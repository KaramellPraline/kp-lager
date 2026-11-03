"""M45: Felder (Einsatz, Scheibe), gespeichertes Etiketten-Layout, Einstellungen in Export/Backup,
Allgemein-Felder fürs Etikett, Kasten drehen."""

import json
import re
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app import backup, catalog, importer, labels, restore, typesettings
from app.db import connect
from tests.test_kasten import norb


def test_insert_and_washer_have_outer_diameter_and_thickness() -> None:
    insert = catalog.BY_KEY["insert"]
    assert {"length", "od"} <= {f.key for f in insert.fields}
    name = catalog.name(
        insert, {"kind": "Heat-Set Insert", "thread": "M3", "length": "5", "od": "4.6"}
    )
    assert name == "Heat-Set Insert M3 L5 Ø4.6"
    washer = catalog.BY_KEY["scheibe"]
    assert {"od", "thickness"} <= {f.key for f in washer.fields}
    name = catalog.name(
        washer, {"kind": "Unterlegscheibe", "thread": "M4", "od": "9", "thickness": "0.8"}
    )
    assert name == "Unterlegscheibe M4 Ø9 0.8mm"


def test_netzwerk_group_and_printer_psu_exist() -> None:
    assert catalog.BY_KEY["netzwerkkabel"].group == "Netzwerk"
    assert catalog.BY_KEY["netzteil"].group.startswith("Druckerteile")
    name = catalog.name(catalog.BY_KEY["netzteil"], {"kind": "Netzteil", "volt": "24", "amp": "10"})
    assert name == "Netzteil 24V 10A"


def test_saved_layout_shows_in_fresh_preview(client: TestClient) -> None:
    default = client.get("/etiketten/typ/schraube/vorschau.png").content
    client.post("/etiketten/typ/schraube", data={
        "qr": "none", "t_0": "{thread}x{length}", "w_0": "3", "a_0": "center"})  # fmt: skip
    after = client.get("/etiketten/typ/schraube/vorschau.png", params={"msg": "x"}).content
    assert after != default  # ohne Layout-Parameter gilt das gespeicherte Layout
    client.post("/etiketten/typ/schraube", data={"reset": "1"})
    assert client.get("/etiketten/typ/schraube/vorschau.png").content == default


def test_layout_and_settings_in_export_restore_and_backup(
    client: TestClient, tmp_path: Path
) -> None:
    client.post("/etiketten/typ/schraube", data={"qr": "right", "t_0": "{thread} {od}", "w_0": "2"})
    conn = connect(tmp_path / "lager.db")
    dump = importer.export(conn)
    assert any(
        r["key"] == "schraube" and "right" in r["label_layout"] for r in dump["type_setting"]
    )
    fresh = connect(tmp_path / "neu.db")
    parsed = restore.parse_dump(json.dumps(dump))
    assert parsed is not None
    restore.restore(fresh, parsed)
    assert '"right"' in typesettings.get(fresh, "schraube")["label_layout"]
    files = backup.run(tmp_path, tmp_path / "bk", day=date(2026, 1, 2))
    saved = connect(files[0])
    assert '"right"' in typesettings.get(saved, "schraube")["label_layout"]


def test_all_item_fields_usable_on_labels(client: TestClient, tmp_path: Path) -> None:
    page = client.get("/etiketten/typ/schraube").text
    for token in ("{qty}", "{unit}", "{model}", "{notes}", "{tags}", "{price}", "{full_name}"):
        assert f'data-token="{token}"' in page
    assert dict(labels.EXTRA_FIELDS)["qty"] == "Menge"


def test_box_view_rotates_handle_to_bottom_by_default(client: TestClient) -> None:
    k = norb(client)

    def blocked(url: str) -> list[tuple[float, float]]:
        html = client.get(url).text
        svg = re.search(r'viewBox="-12 -12 (\d+) (\d+)"', html)
        assert svg
        rects = re.findall(r'<rect x="([\d.]+)" y="([\d.]+)"[^>]*class="tv-blocked"', html)
        return [(float(x), float(y)) for x, y in rects]

    html = client.get(f"/n/{k}").text
    assert "Kiste drehen" in html and "Griff unten" in html
    assert re.search(r'viewBox="-12 -12 724 524"', html)  # 7 Spalten × 5 Zeilen nach dem Drehen
    default = blocked(f"/n/{k}")  # 270°: Griff unten, lange Seite waagerecht
    assert len(default) == 3 and all(y > 300 for _, y in default)
    original = blocked(f"/n/{k}?drehen=0")  # unrotiert: Griff links (merkt sich der Browser)
    assert all(x < 50 for x, _ in original)
    assert "Griff links" in client.get(f"/n/{k}").text
