"""M40: Mindestbestand je Typ, Platz-Vorschlag, Zählen per Waage, Ablauf-Erinnerung."""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import expiry, placement, repo, typesettings, weighing
from app.db import connect
from app.repo import LagerError


def _box(c: TestClient, name: str = "Kiste") -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def _nut(c: TestClient, box: int, thread: str, qty: str) -> int:
    c.post("/neu", data={"typ": "mutter", "f_kind": "Sechskantmutter", "f_thread": thread,
                         "qty": qty, "target": box, "force": "1"})  # fmt: skip
    rows = c.get(f"/api/v1/containers/{box}").json()["items"]
    return int(max(i["id"] for i in rows))


def test_type_min_qty_and_item_override(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    m3 = _nut(client, box, "M3", "10")
    m4 = _nut(client, box, "M4", "100")
    r = client.post("/sortiment/mutter/einstellungen", data={"min_qty": "50"})
    assert "Einstellungen für den Typ gespeichert" in r.text and "Mindestbestand 50" in r.text
    shop = client.get("/einkauf").text
    assert (
        "Sechskantmutter M3" in shop
        and "min. 50 (Typ)" in shop
        and "Sechskantmutter M4" not in shop
    )
    conn = connect(tmp_path / "lager.db")
    row = next(i for i in repo.shopping_list(conn) if i["id"] == m3)
    assert row["need"] == 40
    repo.update_item(conn, m3, min_qty=5)  # Teil überschreibt den Typ
    assert all(i["id"] != m3 for i in repo.shopping_list(conn))
    repo.update_item(conn, m4, min_qty=200)
    assert any(i["id"] == m4 for i in repo.shopping_list(conn))
    assert typesettings.effective_min(conn, repo.get_item(conn, m4)) == (200, False)
    assert "leer = Typ-Standard 50" in client.get(f"/items/{m3}").text
    assert (
        "ganze Zahl" in client.post("/sortiment/mutter/einstellungen", data={"min_qty": "-1"}).text
    )


def test_place_suggestion_prefers_same_fields(client: TestClient, tmp_path: Path) -> None:
    a, b, empty = _box(client, "Box A"), _box(client, "Box B"), _box(client, "Leer")
    _nut(client, a, "M3", "10")
    _nut(client, b, "M4", "10")
    _nut(client, b, "M5", "10")
    rows = client.get("/neu/platz", params={"typ": "mutter", "f_thread": "M4"}).json()
    assert rows[0]["id"] == b and "1 gleiche" in rows[0]["reason"]
    assert {r["id"] for r in rows} >= {a, b, empty}
    assert next(r for r in rows if r["id"] == empty)["reason"] == "leer"
    conn = connect(tmp_path / "lager.db")
    assert placement.suggest(conn, "schraube")[0]["reason"] == "leer"  # nichts Ähnliches
    page = client.get("/neu?typ=mutter").text
    assert 'class="chips place-sugg"' in page


def test_weighing(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    nut = _nut(client, box, "M3", "10")
    r = client.post(f"/items/{nut}/stueckgewicht", data={"count": "20", "grams": "25", "tare": "5"})
    assert "Stückgewicht 1 g gespeichert" in r.text
    r = client.post(f"/items/{nut}/zaehlen", data={"gross": "105,4"})
    assert "Gewogen: 100 Stück" in r.text
    conn = connect(tmp_path / "lager.db")
    assert repo.get_item(conn, nut)["qty"] == 100
    with pytest.raises(LagerError):
        weighing.calibrate(conn, nut, "0", "10")
    with pytest.raises(LagerError):
        weighing.calibrate(conn, nut, "5", "3", "5")
    assert "kein Gewicht" in client.post(f"/items/{nut}/zaehlen", data={"gross": "abc"}).text


def test_expiry(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "kleber", "f_kind": "Sekundenkleber", "target": box})
    conn = connect(tmp_path / "lager.db")
    glue = conn.execute("SELECT id FROM item WHERE ctype = 'kleber'").fetchone()["id"]
    typesettings.save(conn, "kleber", None, 6)
    msg = expiry.opened_now(conn, glue, today=date(2026, 8, 31))
    assert "haltbar bis 2027-02-28" in msg
    assert repo.get_item(conn, glue)["opened"] == "2026-08-31"
    assert expiry.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    repo.update_item(conn, glue, expires=date.today().isoformat())
    page = client.get("/ablauf").text
    assert "Sekundenkleber" in page and "heute" in page
    assert "Läuft ab" in client.get("/").text and 'href="/ablauf"' in client.get("/").text
    r = client.post(f"/items/{glue}/verlaengern", data={"months": "3", "back": "/ablauf"})
    assert "Haltbar bis" in r.text
    r = client.post(f"/items/{glue}/verbraucht", data={"back": "/ablauf"})
    assert "verbraucht" in r.text and repo.get_item(conn, glue)["archived"] == 1
    assert "Heute geöffnet" in client.get(f"/items/{glue}").text
