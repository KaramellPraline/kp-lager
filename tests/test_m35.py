"""M35: Einkäufe/Lieferanten, Karten, Inventur, Stücklisten-Abgleich, externes Backup, Startseite."""

import sqlite3
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app import backup, cards, codes, inventory, projects, purchases, repo, scheduler
from app.db import connect


def _box(c: TestClient, name: str = "Regal") -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": "shelf"})
    return int(r.url.path.rsplit("/", 1)[1])


def _item(c: TestClient, box: int, text: str, cat: str = "CNS") -> int:
    c.post("/quickadd", data={"mode": "item", "text": text, "target": box, "cat": cat})
    items = c.get(f"/api/v1/containers/{box}").json()["items"]
    return int(next(i["id"] for i in items if i["name"] in text))


def test_purchases_and_suppliers(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    item = _item(client, box, "M3 Muttern")
    r = client.post(f"/items/{item}/purchases", data={
        "supplier": "Reichelt", "qty": "100", "price": "0,02", "url": "https://r.example/m3"})  # fmt: skip
    assert "Einkauf erfasst" in r.text and "Reichelt" in r.text and "0,02" in r.text
    client.post(
        f"/items/{item}/purchases", data={"supplier": "reichelt", "qty": "50", "price": "0,03"}
    )
    conn = connect(tmp_path / "lager.db")
    assert [s["name"] for s in purchases.suppliers(conn)] == ["Reichelt"]  # Groß/klein = gleich
    assert purchases.suppliers(conn)[0]["n"] == 2
    assert repo.get_item(conn, item)["price"] == 0.03  # letzter Preis gilt
    assert purchases.last_supplier(conn, item) == "Reichelt"
    page = client.get("/lieferanten").text
    assert "Reichelt" in page and "2 Einkäufe" in page
    sid = purchases.suppliers(conn)[0]["id"]
    assert "M3 Muttern" in client.get(f"/lieferanten/{sid}").text
    client.post(
        f"/lieferanten/{sid}", data={"url": "https://reichelt.de", "note": "Rabatt ab 50 €"}
    )
    assert "Rabatt ab 50" in client.get(f"/lieferanten/{sid}").text
    assert (
        "Preis darf nicht negativ"
        in client.post(f"/items/{item}/purchases", data={"price": "-1"}).text
    )


def test_cards_for_items_and_containers(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    item = _item(client, box, "ESP32", "CMP")
    r = client.post(f"/items/{item}/cards", data={
        "kind": "pinout", "title": "Pinbelegung J1", "body": "1; VCC; 3,3 V\n2; GND\n# Kommentar"})  # fmt: skip
    assert "Pinbelegung J1" in r.text and "<td>VCC</td>" in r.text and "3,3 V" in r.text
    conn = connect(tmp_path / "lager.db")
    cid = cards.for_item(conn, item)[0]["id"]
    assert cards.pinout_rows("1 VCC 3.3V") == [["1", "VCC", "3.3V"]]
    client.post(f"/cards/{cid}/edit", data={"title": "J1 neu", "body": "1; 5V"})
    assert "J1 neu" in client.get(f"/items/{item}").text
    client.post(f"/n/{box}/cards", data={"title": "Regalmaße", "body": "120 cm breit"})
    assert "120 cm breit" in client.get(f"/n/{box}").text
    client.post(f"/cards/{cid}/delete")
    assert "J1 neu" not in client.get(f"/items/{item}").text


def test_inventory_round(client: TestClient, tmp_path: Path) -> None:
    box = _box(client, "Werkzeugregal")
    a = _item(client, box, "5 Bohrer", "TOL")
    b = _item(client, box, "Zange", "TOL")
    assert "Werkzeugregal" in client.get("/inventur").text
    assert "Inventur fällig" in client.get("/").text
    page = client.get(f"/inventur/{box}").text
    assert "0 von 2 geprüft" in page
    r = client.post(f"/inventur/item/{a}", data={"qty": "4"})
    assert "Menge 5 → 4" in r.text and "1 von 2 geprüft" in r.text
    conn = connect(tmp_path / "lager.db")
    assert repo.get_item(conn, a)["qty"] == 4
    code = repo.get_item(conn, b)["code"]
    assert "bestätigt" in client.post(f"/inventur/{box}/scan", data={"code": code}).text
    assert "gehört nicht" in client.post(f"/inventur/{box}/scan", data={"code": "ART-999"}).text
    r = client.post(f"/inventur/{box}/done")
    assert "Inventur abgeschlossen" in r.text and "Werkzeugregal" not in r.text.split("<h1>")[1]
    assert inventory.due(conn) == []
    assert inventory.items(conn, box)[0]["checked"] is False  # neue Runde


def test_project_bom_compare_and_shopping(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    schraube = _item(client, box, "10 M3 Schrauben")
    pid = projects.create(conn := connect(tmp_path / "lager.db"), "Wetterstation")
    projects.add_line(conn, pid, schraube, qty=25)
    projects.add_line(conn, pid, None, name="BME280 Sensor", qty=1)
    bom = projects.compare(conn, pid)
    assert bom["counts"] == {"ok": 0, "teil": 1, "fehlt": 1, "geholt": 0}
    assert [r["short"] for r in bom["lines"]] == [15, 1] and not bom["complete"]
    page = client.get(f"/projekte/{pid}").text
    assert "Es fehlt etwas" in page and "zu wenig (fehlt 15)" in page
    r = client.post(f"/projekte/{pid}/einkauf")
    assert "1 Teile auf der Einkaufsliste" in r.text
    row = next(i for i in repo.shopping_list(conn) if i["id"] == schraube)
    assert row["need"] == 15


def test_extern_backup_mirror(tmp_path: Path) -> None:
    data, extern = tmp_path / "data", tmp_path / "nas"
    connect(data / "lager.db").close()
    assert scheduler.extern_tick(data) == "Kein externes Ziel eingestellt"
    conn = connect(data / "lager.db")
    codes.set_setting(conn, "backup_extern", str(extern))
    assert scheduler.extern_tick(data) == "Noch kein lokales Backup für heute"
    scheduler.tick(data)
    assert "Extern gesichert" in scheduler.extern_tick(data)
    assert (extern / f"lager-{date.today().isoformat()}.db").exists()
    assert not list(extern.glob(".*.tmp"))
    assert scheduler.extern_tick(data) == "Heute schon extern gesichert"
    assert codes.get_setting(conn, "backup_extern_error", "x") == ""
    blocked = tmp_path / "datei"
    blocked.write_text("x")  # Ziel ist eine Datei -> Fehler wird gemeldet, nicht geworfen
    codes.set_setting(conn, "backup_extern", str(blocked / "sub"))
    assert "fehlgeschlagen" in scheduler.extern_tick(data, force=True)
    assert codes.get_setting(conn, "backup_extern_error", "") != ""
    assert backup.todays_files(data / "backups")


def test_home_is_task_overview_and_more_is_grouped(client: TestClient) -> None:
    box = _box(client)
    _item(client, box, "Lötzinn", "CNS")
    home = client.get("/").text
    assert "built-in method" not in home and "<dt>Teile</dt><dd>1</dd>" in home
    assert 'class="task-cards"' in home and "Inventur fällig" in home and 'class="kpis"' in home
    more = client.get("/mehr").text
    for head in (">Lager<", ">Werkstatt<", ">Einkauf<", ">System<"):
        assert head in more
    assert "/lieferanten" in more and "/inventur" in more
    nav = client.get("/").text.split('class="bottomnav')[1]
    assert 'href="/neu/go"' in nav and 'href="/suche"' in nav and 'href="/einkauf"' not in nav


def test_add_tab_remembers_last_tab(client: TestClient) -> None:
    assert client.get("/neu/go", follow_redirects=False).headers["location"] == "/neu"
    client.get("/neu/behaelter")
    assert client.get("/neu/go", follow_redirects=False).headers["location"] == "/neu/behaelter"
    client.get("/neu/bin")
    assert client.get("/neu/go", follow_redirects=False).headers["location"] == "/neu/bin"


def test_migration_019_tables(tmp_path: Path) -> None:
    conn = connect(tmp_path / "lager.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 19
    for t in ("supplier", "purchase", "card"):
        assert conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0] == 0
    try:
        conn.execute("INSERT INTO card (title) VALUES ('x')")
        raise AssertionError("Karte ohne Besitzer darf nicht gehen")
    except sqlite3.IntegrityError:
        pass
