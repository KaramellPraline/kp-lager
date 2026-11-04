"""M51: Druck-Fallback in die Warteschlange, Einzelteile, Kunststoff = 100 − Zusatz, A4 aus Behälter,
API-Schlüssel abschaltbar."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import catalog, d30
from app.config import Settings
from app.db import connect
from app.repo import LagerError
from app.web import create_app


def box(client: TestClient) -> int:
    r = client.post(
        "/containers", data={"name": "Regal", "kind": "toolbox"}, follow_redirects=False
    )
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


@pytest.fixture
def printer_client(tmp_path: Path) -> Iterator[TestClient]:
    """App mit aktivem D30-Direktdruck."""
    s = Settings(data_dir=tmp_path, base_url="https://lager.test", d30=True)
    with TestClient(create_app(s), follow_redirects=True) as c:
        yield c


def test_failed_print_goes_to_queue_automatically(
    printer_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kw: object) -> int:
        raise LagerError("Druck-Agent offline")

    monkeypatch.setattr(d30, "print_codes", broken)
    c = printer_client
    c.post("/neu/druckmodus", data={"mode": "einzel"})
    b = box(c)
    r = c.post("/neu", data={"typ": "mutter", "f_thread": "M4", "target": str(b)})
    assert "Druck nicht möglich (Druck-Agent offline)" in r.text
    assert "in der Druck-Warteschlange" in r.text
    assert "M4" in c.get("/labels/queue").text  # liegt wirklich in der Warteschlange


def test_nav_has_printer_icon_and_drucken(client: TestClient) -> None:
    page = client.get("/").text
    assert "<span>Drucken</span>" in page and "<span>Etiketten</span>" not in page


def test_filament_is_single_pieces_and_duplicable(client: TestClient, tmp_path: Path) -> None:
    b = box(client)
    r = client.post("/neu", data={"typ": "filament", "f_brand": "Sunlu", "f_plastic": "PETG",
                                  "f_color": "Weiß", "qty": "3", "target": str(b)})  # fmt: skip
    assert "3 Teile angelegt: 3× Sunlu PETG Weiß" in r.text
    conn = connect(tmp_path / "lager.db")
    rows = conn.execute("SELECT code, qty FROM item WHERE ctype = 'filament'").fetchall()
    assert len(rows) == 3 and all(x["qty"] == 1 for x in rows)
    assert len({x["code"] for x in rows}) == 3  # jede Spule eigener Code
    item = conn.execute("SELECT id FROM item WHERE ctype = 'filament' LIMIT 1").fetchone()
    assert f"/neu?typ=filament&vorlage={item['id']}" in client.get(f"/items/{item['id']}").text
    page = client.get(f"/neu?typ=filament&vorlage={item['id']}").text
    assert 'value="Sunlu"' in page and 'value="Weiß"' in page  # Duplizieren füllt vor
    assert "Einzelteile" in page and "checked disabled" in page


def test_single_checkbox_for_normal_types(client: TestClient, tmp_path: Path) -> None:
    page = client.get("/neu?typ=mutter").text
    assert 'name="single"' in page and "checked disabled" not in page
    b = box(client)
    client.post("/neu", data={"typ": "mutter", "f_thread": "M5", "qty": "2", "single": "1",
                              "target": str(b)})  # fmt: skip
    conn = connect(tmp_path / "lager.db")
    assert conn.execute("SELECT COUNT(*) FROM item WHERE ctype='mutter'").fetchone()[0] == 2
    client.post("/neu", data={"typ": "mutter", "f_thread": "M6", "qty": "50", "target": str(b)})
    row = conn.execute("SELECT qty FROM item WHERE name LIKE '%M6%'").fetchone()
    assert row["qty"] == 50  # ohne Haken: eine Position mit Menge


def test_plastic_share_is_100_minus_additive() -> None:
    t = catalog.BY_KEY["filament"]
    assert all(f.key != "plastic_pct" for f in t.fields)
    v = {
        "brand": "X",
        "plastic": "PA12",
        "additive": "Carbonfaser",
        "additive_pct": "20",
        "color": "Schwarz",
    }
    assert catalog.name(t, v) == "X PA12 80% + CF 20% Schwarz"
    v["additive_pct"] = "12,5"
    assert (
        catalog.derive(t, catalog.derive(t, {**v, "additive_pct": "12.5"}))["material"]
        == "PA12 87.5% + CF 12.5%"
    )
    assert catalog.name(t, {"brand": "X", "plastic": "PLA", "color": "Rot"}) == "X PLA Rot"
    assert (
        catalog.derive(t, {"plastic": "PETG", "additive": "Glasfaser"})["material"] == "PETG + GF"
    )


def test_a4_new_label_from_container(client: TestClient) -> None:
    b = box(client)
    client.post(f"/n/{b}/items", data={"name": "Zange"})
    page = client.get("/a4").text
    assert 'name="container"' in page and "Regal" in page
    client.post(f"/n/{b}/code")  # Behälter bekommt einen Code, falls noch keiner
    r = client.post(
        "/a4/add", data={"type": "box", "container": str(b), "contents": "1", "w": "100", "h": "60"}
    )
    assert "A4-Warteschlange (1)" in r.text and "Regal" in r.text
    assert "Bitte einen Titel" in client.post("/a4/add", data={"type": "box"}).text


def test_api_write_key_can_be_turned_off(client: TestClient) -> None:
    b = box(client)
    body = {"container": str(b), "text": "Debug-Teil"}
    assert client.post("/api/v1/items", json=body).status_code == 401  # Standard: Schlüssel nötig
    page = client.get("/settings").text
    assert "API: Schreiben nur mit Schlüssel" in page
    client.post("/settings", data={})  # Schalter aus (Checkbox nicht gesetzt)
    r = client.post("/api/v1/items", json=body)
    assert r.status_code in (200, 201), r.text
    client.post("/settings", data={"api_write_key": "1"})
    assert client.post("/api/v1/items", json=body).status_code == 401
