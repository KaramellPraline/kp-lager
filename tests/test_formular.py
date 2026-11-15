"""Paket 4: Hinzufügen = Bearbeiten – ein gemeinsames Formular für Teile und Behälter."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import catalog, materials, repo
from app.db import connect

FIELDS = (
    'id="f_thread"', 'id="name"', 'id="qty"', 'id="unit"', 'id="target"', 'id="min_qty"',
    'id="order_qty"', 'id="price"', 'id="order_url"', 'id="model"', 'id="datasheet_url"',
    'id="expires"', 'id="opened"', 'id="tags"', 'id="notes"', 'id="profile-sel"',
)  # fmt: skip


def _box(c: TestClient, name: str = "Regal", kind: str = "toolbox") -> int:
    r = c.post("/containers", data={"name": name, "kind": kind}, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def _count(tmp_path: Path, table: str = "item") -> int:
    return int(
        connect(tmp_path / "lager.db").execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    )


def _screw(c: TestClient, box: int, **extra: str) -> int:
    data = {"typ": "schraube", "f_thread": "M3", "f_length": "10", "qty": "40", "target": str(box)}
    c.post("/neu", data={**data, **extra})
    return int(c.get(f"/api/v1/containers/{box}").json()["items"][-1]["id"])


def test_same_form_for_create_and_edit(client: TestClient) -> None:
    box = _box(client)
    new = client.get("/neu?typ=schraube").text
    iid = _screw(client, box)
    edit = client.get(f"/items/{iid}/bearbeiten").text
    for page in (new, edit):
        assert 'class="card stack teil-form"' in page and 'id="typ-liste"' in page
        assert all(f in page for f in FIELDS), [f for f in FIELDS if f not in page]
    # Anlegen leer, Bearbeiten vorbefüllt
    assert re.search(r'id="f_thread"[^>]*value=""', new) and re.search(
        r'id="qty"[^>]*value=""', new
    )
    assert re.search(r'id="f_thread"[^>]*value="M3"', edit)
    assert re.search(r'id="qty"[^>]*value="40"', edit)
    assert f'<option value="{box}" selected>' in edit
    assert 'action="/items/' + str(iid) + '/bearbeiten"' in edit and "Speichern" in edit
    # Teil-Seite führt nur noch über dieses Formular zum Bearbeiten
    page = client.get(f"/items/{iid}").text
    assert f'href="/items/{iid}/bearbeiten"' in page and 'id="edit-box"' not in page
    assert f'action="/items/{iid}/edit"' not in page and f'action="/items/{iid}/typ"' not in page


def test_create_takes_common_fields(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    iid = _screw(
        client, box, min_qty="10", price="0.05", notes="aus Restposten", model="DIN912",
        expires="2030-01-01", tags="restposten",
    )  # fmt: skip
    item = repo.get_item(connect(tmp_path / "lager.db"), iid)
    assert item["min_qty"] == 10 and item["price"] == 0.05 and item["notes"] == "aus Restposten"
    assert item["model"] == "DIN912" and item["expires"] == "2030-01-01"
    assert "restposten" in item["tags"] and "schraube" in item["tags"]


def test_edit_changes_existing_item_without_creating(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    other = _box(client, "Kiste", "box")
    iid = _screw(client, box)
    before = _count(tmp_path)
    r = client.post(f"/items/{iid}/bearbeiten", data={
        "typ": "schraube", "f_thread": "M3", "f_length": "12", "qty": "35", "unit": "Stk",
        "target": str(other), "min_qty": "20", "price": "0,08", "notes": "neu sortiert",
        "order_url": "https://example.org/m3", "expires": "", "tags": "",
    })  # fmt: skip
    assert r.url.path == f"/items/{iid}" and "Gespeichert" in r.text
    assert _count(tmp_path) == before
    item = repo.get_item(connect(tmp_path / "lager.db"), iid)
    assert item["name"] == "M3x12" and item["qty"] == 35 and item["container_id"] == other
    assert item["min_qty"] == 20 and item["price"] == 0.08 and item["notes"] == "neu sortiert"
    assert item["order_url"] == "https://example.org/m3"
    assert catalog.values_of(item) == {"thread": "M3", "length": "12"}
    # eigener Anzeigename bleibt, leer = wieder aus den Feldern
    client.post(f"/items/{iid}/bearbeiten", data={"typ": "schraube", "f_thread": "M3",
                "f_length": "12", "name": "Schraube kurz", "qty": "35"})  # fmt: skip
    assert repo.get_item(connect(tmp_path / "lager.db"), iid)["name"] == "Schraube kurz"
    assert (
        'id="name" name="name" value="Schraube kurz"' in client.get(f"/items/{iid}/bearbeiten").text
    )


def test_type_change_when_editing(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    iid = _screw(client, box)
    # Typ wechseln: Felder mit gleichem Schlüssel bleiben vorbefüllt
    page = client.get(f"/items/{iid}/bearbeiten?typ=mutter").text
    assert 'name="typ" value="mutter"' in page and re.search(r'id="f_thread"[^>]*value="M3"', page)
    assert 'id="f_length"' not in page
    before = _count(tmp_path)
    client.post(f"/items/{iid}/bearbeiten", data={"typ": "mutter", "f_thread": "M4", "qty": "40"})
    item = repo.get_item(connect(tmp_path / "lager.db"), iid)
    assert _count(tmp_path) == before
    assert item["ctype"] == "mutter" and "M4" in item["name"] and "mutter" in item["tags"]
    assert catalog.values_of(item) == {"thread": "M4"}
    # Typ entfernen: Name muss dann angegeben sein
    assert "Name fehlt" in client.post(f"/items/{iid}/bearbeiten", data={"typ": ""}).text
    client.post(f"/items/{iid}/bearbeiten", data={"typ": "", "name": "Mutter lose", "qty": "1"})
    item = repo.get_item(connect(tmp_path / "lager.db"), iid)
    assert item["ctype"] is None and item["name"] == "Mutter lose"


def test_required_fields_apply_when_editing(client: TestClient) -> None:
    box = _box(client)
    iid = _screw(client, box)
    client.post("/neu/pflicht", data={"typ": "schraube", "req_length": "1"})
    r = client.post(f"/items/{iid}/bearbeiten", data={"typ": "schraube", "f_thread": "M3"})
    assert "Pflichtfeld fehlt: Länge" in r.text
    assert 'data-req="1"' in client.get(f"/items/{iid}/bearbeiten").text


def test_material_profile_in_shared_form(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/neu", data={
        "typ": "filament", "f_brand": "Prusament", "f_plastic": "PETG", "f_weight": "1",
        "qty": "1", "target": str(box), "spec_nozzle_min": "230",
    })  # fmt: skip
    iid = client.get(f"/api/v1/containers/{box}").json()["items"][-1]["id"]
    conn = connect(tmp_path / "lager.db")
    specs = materials.specs(repo.get_item(conn, iid))
    assert (
        specs["nozzle_min"] == "230" and specs["weight"] == "1000" and specs["brand"] == "Prusament"
    )
    page = client.get(f"/items/{iid}/bearbeiten").text
    assert 'name="spec_nozzle_min" value="230"' in page and "Max. Volumenfluss" in page
    assert 'name="spec_brand"' not in page.split('data-profile="fil"')[1].split("</fieldset>")[0]
    before = _count(tmp_path)
    client.post(f"/items/{iid}/bearbeiten", data={
        "typ": "filament", "f_brand": "Prusament", "f_plastic": "PETG", "f_color": "Orange",
        "f_weight": "1", "qty": "1", "material": "fil", "spec_nozzle_min": "240",
        "spec_dry_temp": "65",
    })  # fmt: skip
    item = repo.get_item(conn, iid)
    specs = materials.specs(item)
    assert _count(tmp_path) == before and item["material"] == "fil"
    assert specs["nozzle_min"] == "240" and specs["dry_temp"] == "65" and specs["color"] == "Orange"
    assert specs["weight"] == "1000" and "Orange" in item["name"]
    # Teil ohne Typ: Profil im Formular wählbar (Elektronik-Datenblatt)
    client.post(f"/n/{box}/items", data={"name": "Sensor", "qty": "2"})
    sid = client.get(f"/api/v1/containers/{box}").json()["items"][-1]["id"]
    client.post(f"/items/{sid}/bearbeiten", data={
        "typ": "", "name": "Sensor", "qty": "2", "material": "cmp",
        "spec_function": "Temperatursensor", "spec_interface": "I2C",
    })  # fmt: skip
    sensor = repo.get_item(conn, sid)
    assert sensor["material"] == "cmp" and materials.specs(sensor)["interface"] == "I2C"
    assert "<dd>I2C</dd>" in client.get(f"/items/{sid}").text


def test_container_create_and_edit_same_form(client: TestClient, tmp_path: Path) -> None:
    room = _box(client, "Werkstatt", "room")
    shelf = _box(client, "Regal", "shelf")
    new = client.get("/neu/behaelter?art=box").text
    client.post("/containers", data={"name": "Kiste rot", "kind": "box", "parent_id": str(room),
                                     "notes": "Kabel", "tare": "300"})  # fmt: skip
    kid = int(connect(tmp_path / "lager.db").execute("SELECT MAX(id) FROM container").fetchone()[0])
    edit = client.get(f"/n/{kid}/bearbeiten").text
    for page in (new, edit):
        assert 'class="card stack node-form"' in page and 'id="art-liste"' in page
        for f in ('id="name"', 'id="parent_id"', 'id="code"', 'id="tare"', 'id="notes"'):
            assert f in page
    assert 'id="name" name="name" value="Kiste rot"' in edit and ">Kabel</textarea>" in edit
    assert 'value="300"' in edit and f'<option value="{room}" selected>' in edit
    before = _count(tmp_path, "container")
    r = client.post(f"/n/{kid}/bearbeiten", data={"name": "Kiste blau", "kind": "eurobox",
                    "parent_id": str(shelf), "notes": "", "tare": "", "dims": "neu",
                    "dims_custom": "400x300x220"})  # fmt: skip
    assert r.url.path == f"/n/{kid}" and _count(tmp_path, "container") == before
    node = repo.get_container(connect(tmp_path / "lager.db"), kid)
    assert node is not None and node["name"] == "Kiste blau" and node["kind"] == "eurobox"
    assert node["parent_id"] == shelf and node["dims"] == "400x300x220" and node["tare"] is None
    page = client.get(f"/n/{kid}").text
    assert f'href="/n/{kid}/bearbeiten"' in page and 'id="edit-box"' not in page
    # nicht in sich selbst verschieben
    assert f'<option value="{kid}"' not in client.get(f"/n/{kid}/bearbeiten").text


def test_item_page_quick_actions(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    iid = _screw(client, box)
    page = client.get(f"/items/{iid}").text
    head = page.split('id="aktionen"')[1].split("</section>")[0]
    # Entnehmen: Menge ist vorbelegt (1 Tap), Schnellwahl + Knopf (2 Taps)
    assert f'action="/items/{iid}/take"' in head and 'id="take-qty" name="qty" value="1"' in head
    assert f'action="/items/{iid}/einlagern"' in head and f'action="/carry/item/{iid}"' in head
    assert f'href="/items/{iid}/bearbeiten"' in head and "/labels/quick/item/" in head
    for fold in ("verlauf", "einkaeufe", "karten-box", "waage", "ablauf", "verleihen", "gefahr"):
        assert f'<details class="fold' in page and f'id="{fold}"' in page
    r = client.post(f"/items/{iid}/einlagern", data={"qty": "5"})
    assert "5 eingelagert" in r.text
    assert repo.get_item(connect(tmp_path / "lager.db"), iid)["qty"] == 45
    sw = client.get("/sw.js").text
    assert "einlagern" in sw.split("QUEUE_PATHS")[1].split(";")[0]


def test_navigation_and_more_are_lean(client: TestClient) -> None:
    side = client.get("/").text.split('class="sidenav"')[1].split("</aside>")[0]
    for href in ("/", "/neu/go", "/scan", "/suche", "/labels", "/mehr"):
        assert f'href="{href}"' in side
    assert 'href="/einkauf"' not in side and 'href="/platz"' not in side
    more = client.get("/mehr").text
    assert "Selten gebraucht" in more and "/codes" in more.split("Selten gebraucht")[1]
    labels = client.get("/etiketten/typ").text
    assert 'data-a="Befestigung"' in labels and 'id="type-filter"' in labels
    mobile = client.get("/neu?typ=schraube").text
    assert 'href="#typ-liste"' in mobile and 'class="chips quick-types"' in mobile
