"""M33: Backup täglich, Status, Wert, Nachkaufliste, Trockner, Slicer, Massenbearbeitung, Foto."""

import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import scheduler, slicer, vision
from app.db import connect


def _box(c: TestClient, name: str = "Kiste", kind: str = "box", **extra: str) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": kind, **extra})
    return int(r.url.path.rsplit("/", 1)[1])


def _item(c: TestClient, box: int, text: str, cat: str = "ART", **extra: str) -> None:
    c.post("/quickadd", data={"mode": "item", "cat": cat, "target": box, "text": text, **extra})


def _ids(c: TestClient, box: int) -> dict[str, dict]:  # type: ignore[type-arg]
    return {i["name"]: i for i in c.get(f"/api/v1/containers/{box}").json()["items"]}


# --- Backup & Status ------------------------------------------------------------


def test_daily_backup_once(tmp_path: Path) -> None:
    connect(tmp_path / "lager.db").close()
    files = scheduler.tick(tmp_path, date(2026, 11, 1))
    assert files and (tmp_path / "backups" / "lager-2026-11-01.db").exists()
    assert scheduler.tick(tmp_path, date(2026, 11, 1)) is None  # heute schon gesichert
    assert scheduler.tick(tmp_path, date(2026, 11, 2)) is not None
    assert not list((tmp_path / "backups").glob(".lock-*"))


def test_status_page(client: TestClient) -> None:
    page = client.get("/status").text
    assert "Backup" in page and "Lagerwert" in page and "KI-Gateway" in page
    r = client.post("/status/backup")
    assert "lager-" in r.text
    assert "/status" in client.get("/mehr").text


# --- Wert, Nachkaufliste, Haltbarkeit -----------------------------------------------


def test_value_per_container(client: TestClient) -> None:
    outer = _box(client, "Regal", "shelf")
    inner = _box(client, "Dose", "box", target=str(outer))
    _item(client, inner, "5 Schrauben")
    item_id = _ids(client, inner)["Schrauben"]["id"]
    client.post(f"/items/{item_id}/edit", data={"name": "Schrauben", "qty": "5", "price": "0,50"})
    assert "2,50 €" in client.get(f"/n/{inner}").text
    assert "2,50 €" in client.get(f"/n/{outer}").text  # inkl. Unterbehälter


def test_shopping_list_flow(client: TestClient) -> None:
    box = _box(client)
    _item(client, box, "2 Muttern")
    item_id = _ids(client, box)["Muttern"]["id"]
    client.post(
        f"/items/{item_id}/edit",
        data={"name": "Muttern", "qty": "2", "min_qty": "10", "price": "0,10",
              "expires": "31.12.2099"},
    )  # fmt: skip
    page = client.get("/einkauf").text
    assert "8×" in page and "0,80 €" in page  # bis zum Mindestbestand auffüllen
    assert "Bestellt" in client.post(f"/items/{item_id}/bestellt").text.replace(
        "Doch nicht", "Bestellt"
    )
    assert "bestellt" in client.get("/einkauf").text
    client.post(f"/items/{item_id}/eingetroffen")
    assert _ids(client, box)["Muttern"]["qty"] == 10
    assert "Muttern" not in client.get("/einkauf").text.split("<ul")[1]


def test_expiry_shows_on_status(client: TestClient) -> None:
    box = _box(client)
    _item(client, box, "UV Harz grau", cat="RES")
    item_id = _ids(client, box)["UV Harz grau"]["id"]
    soon = (date.today() + timedelta(days=10)).isoformat()
    client.post(
        f"/items/{item_id}/edit",
        data={"name": "UV Harz grau", "expires": soon, "opened": "2026-01-02"},
    )
    assert "geöffnet 2026-01-02" in client.get(f"/items/{item_id}").text
    assert "UV Harz grau" in client.get("/status").text.split("Haltbarkeit")[1]
    bad = client.post(f"/items/{item_id}/edit", data={"name": "x", "expires": "morgen"})
    assert "kein Datum" in bad.text


# --- Einzelstücke ---------------------------------------------------------------------


def test_cables_and_psus_are_individual(client: TestClient) -> None:
    box = _box(client)
    client.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "USB-A",
                                   "plug_b": "USB-C", "length": "1", "count": "3"})  # fmt: skip
    cables = c = client.get(f"/api/v1/containers/{box}").json()["items"]
    assert len(cables) == 3 and len({i["code"] for i in cables}) == 3
    assert all(i["qty"] is None for i in cables)
    queue = client.get("/labels").text
    assert all(i["code"] in queue for i in c)  # jedes Kabel hat sein Etikett in der Warteschlange
    client.post(
        "/quickadd",
        data={"mode": "item", "cat": "PSU", "target": box, "text": "2 Netzteile 12V 2A"},
    )
    psus = [
        i
        for i in client.get(f"/api/v1/containers/{box}").json()["items"]
        if i["code"].startswith("PSU")
    ]
    assert len(psus) == 2
    page = client.get(f"/n/{box}").text
    assert "Einzelstück" in page and "hx-vals='{\"delta\": -1}'" not in page


# --- Maße, Massenbearbeitung ------------------------------------------------------------


def test_eurobox_dims(client: TestClient) -> None:
    assert "600x400x170" in client.get("/").text  # Auswahlliste (JSON), Anzeige per JS
    box = _box(client, "Eurobox groß", "eurobox", dims="600x400x170")
    assert "600 × 400 × 170 mm" in client.get(f"/n/{box}").text
    other = _box(client, "Kiste eigene", "crate", dims_other="45 x 35 x 20")
    assert "45 × 35 × 20 mm" in client.get(f"/n/{other}").text


def test_bulk_move_and_edit(client: TestClient) -> None:
    a, b = _box(client, "A"), _box(client, "B")
    for name in ("Eins", "Zwei", "Drei"):
        _item(client, a, name)
    ids = _ids(client, a)
    page = client.get(f"/auswahl?node={a}").text
    assert "Eins" in page and "Mehrere bearbeiten" in page
    refs = [f"i{ids[n]['id']}" for n in ("Eins", "Zwei")]
    r = client.post(
        "/bulk", data={"ref": refs, "action": "move", "target": str(b), "back": "/auswahl"}
    )
    assert "2 verschoben" in r.text
    assert set(_ids(client, b)) == {"Eins", "Zwei"} and set(_ids(client, a)) == {"Drei"}
    client.post("/bulk", data={"ref": refs, "action": "min", "value": "7", "back": "/auswahl"})
    client.post(
        "/bulk", data={"ref": refs, "action": "tag", "value": "bulktag", "back": "/auswahl"}
    )
    assert client.get("/api/v1/types").json()[0]["name"] == "bulktag"
    r = client.post(
        "/bulk", data={"ref": refs[0], "action": "cat", "value": "TOL", "back": "/auswahl"}
    )
    assert _ids(client, b)["Eins"]["code"].startswith("TOL-")
    r = client.post(
        "/bulk", data={"ref": f"c{b}", "action": "move", "target": str(a), "back": "/auswahl"}
    )
    assert "1 verschoben" in r.text
    assert "Nichts ausgewählt" in client.post("/bulk", data={"action": "move"}).text


# --- Trockner ---------------------------------------------------------------------------


def test_dryer(client: TestClient) -> None:
    box = _box(client)
    _item(client, box, "PETG weiß", cat="FIL")
    item_id = _ids(client, box)["PETG weiß"]["id"]
    page = client.get("/trockner").text
    assert "PETG" in page and "65 °C" in page
    client.post("/trockner/start", data={"item_id": item_id, "program_id": 2})
    assert "Nichts im Trockner" not in client.get("/trockner").text
    assert "läuft" in client.get(f"/items/{item_id}").text
    client.post("/trockner/1/fertig")
    assert "Nichts im Trockner" in client.get("/trockner").text
    client.post("/trockner/programme", data={"name": "PETG-CF", "temp_c": "70", "hours": "8"})
    assert "PETG-CF" in client.get("/trockner").text
    assert (
        "Temperatur"
        in client.post(
            "/trockner/programme", data={"name": "x", "temp_c": "500", "hours": "8"}
        ).text
    )


# --- Slicer -----------------------------------------------------------------------------

GCODE = """; generated by Creality Print
; filament_type = PLA;PETG
; filament_colour = #FFFFFF;#FF0000
G1 X0 Y0
; filament used [mm] = 3500.00, 1000.00
; filament used [g] = 10.50, 3.00
; estimated printing time (normal mode) = 1h 2m 3s
"""


def test_parse_gcode_and_3mf() -> None:
    job = slicer.parse_bytes(GCODE.encode(), "Benchy.gcode")
    assert job.name == "Benchy" and job.seconds == 3723
    assert [(f.grams, f.type, f.color) for f in job.filaments] == [
        (10.5, "PLA", "#FFFFFF"), (3.0, "PETG", "#FF0000")]  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Metadata/slice_info.config", '<config><plate><filament id="1" type="PETG" '
                   'color="#00FF00" used_m="2.0" used_g="6.1"/><metadata key="prediction" value="600"/></plate></config>')  # fmt: skip
    job = slicer.parse_bytes(buf.getvalue(), "x.gcode.3mf")
    assert job.name == "x" and job.filaments[0].grams == 6.1 and job.seconds == 600
    cura = slicer.parse_bytes(b";Filament used: 1m\n;TIME:90\n", "c.gcode")
    assert round(cura.filaments[0].grams, 1) == 3.0 and cura.seconds == 90


def test_slicer_upload_and_book(client: TestClient) -> None:
    box = _box(client)
    _item(client, box, "PLA weiß", cat="FIL")
    item_id = _ids(client, box)["PLA weiß"]["id"]
    client.post(
        f"/items/{item_id}/specs",
        data={"material": "fil", "spec_material": "PLA", "spec_weight": "1000"},
    )
    r = client.post("/slicer/upload", files={"files": ("Benchy.gcode", GCODE.encode())})
    assert "1 Druck(e) eingelesen" in r.text and "Benchy" in r.text
    r = client.post("/slicer/1/buchen", data={"spool_0": str(item_id), "spool_1": ""})
    assert "−10 g" in r.text or "−11 g" in r.text
    assert "Gebucht" in client.get("/slicer").text
    assert "schon gebucht" in client.post("/slicer/1/buchen", data={"spool_0": str(item_id)}).text
    assert (
        "Keinen Filamentverbrauch"
        in client.post("/slicer/upload", files={"files": ("a.gcode", b"G1 X1")}).text
    )


# --- Foto-Erfassung -------------------------------------------------------------------------


def test_vision_parse() -> None:
    answer = 'Hier: {"items":[{"name":"M3x10 Schraube","cat":"cns","qty":50,"specs":{"a":1}},' \
             '{"name":"","cat":"ART"},{"name":"Lötzinn","cat":"XXX","qty":"viele"}]}'  # fmt: skip
    items = vision.parse(answer)
    assert [i["name"] for i in items] == ["M3x10 Schraube", "Lötzinn"]
    assert items[0]["cat"] == "CNS" and items[0]["qty"] == 50 and items[1]["cat"] == "ART"
    assert items[1]["qty"] is None


def test_photo_endpoint_without_ai(client: TestClient) -> None:
    r = client.post("/api/foto-erkennen", files={"photo": ("a.jpg", b"\xff\xd8\xff")})
    assert r.status_code == 502 and "KI" in json.loads(r.text)["msg"]
