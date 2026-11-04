"""M50: Filament/Harz-Klassen, Komma→Punkt, Feldreihenfolge, Bins verschieben, Bin-Druckdatei."""

import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import a4, catalog, kasten, presets
from app.db import connect


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def box(client: TestClient) -> int:
    r = client.post(
        "/containers", data={"name": "Regal", "kind": "toolbox"}, follow_redirects=False
    )
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def norb(client: TestClient) -> str:
    r = client.post("/containers", data={"name": "Kleinteile", "kind": "sortierkasten",
                                          "code": "SOR-001", "model": "norb16"})  # fmt: skip
    return node_of(r)


def test_filament_form_has_split_material_spool_price_and_presets(client: TestClient) -> None:
    page = client.get("/neu?typ=filament").text
    assert 'class="presets"' in page and 'data-preset="' in page and ">PLA<" in page
    assert page.index('id="presets"') < page.index('id="f_brand"')  # oberste Reihe
    for key in (
        "plastic",
        "plastic_pct",
        "additive",
        "additive_pct",
        "spool_type",
        "spool_weight",
        "price",
    ):
        assert f'id="f_{key}"' in page
    assert page.count('class="frow"') >= 3  # Kunststoff|%|Zusatz|% nebeneinander
    assert 'id="f_material"' not in page


def test_filament_create_composes_material_price_and_spool(
    client: TestClient, tmp_path: Path
) -> None:
    b = box(client)
    r = client.post("/neu", data={
        "typ": "filament", "f_brand": "Fiberthex", "f_plastic": "PA12", "f_plastic_pct": "80",
        "f_additive": "Carbonfaser", "f_additive_pct": "20", "f_color": "Schwarz",
        "f_weight": "0,5", "f_spool_type": "Pappe", "f_spool_weight": "150", "f_price": "24,90",
        "target": str(b),
    })  # fmt: skip
    assert "Fiberthex PA12 80% + CF 20% Schwarz" in r.text
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT * FROM item WHERE ctype = 'filament'").fetchone()
    assert item["price"] == 24.9 and '"spool_type": "Pappe"' in item["specs"]
    assert '"weight": "500"' in item["specs"] and '"spool_weight": "150"' in item["specs"]
    # manuell eingetragener Hersteller wird künftig angeboten (Auswahl + Preset-Ersteller)
    assert "Fiberthex" in catalog.brands(conn, catalog.BY_KEY["filament"])
    assert "Fiberthex" in client.get("/neu?typ=filament").text.split('id="dl_brand"')[1][:600]


def test_preset_save_and_delete(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/neu/preset", data={"typ": "filament", "preset_name": "Meine PETG-Klasse",
                                         "f_brand": "Neuhersteller", "f_plastic": "PETG",
                                         "f_price": "19,99"})  # fmt: skip
    assert "gespeichert" in r.text and "Meine PETG-Klasse" in r.text
    conn = connect(tmp_path / "lager.db")
    p = next(x for x in presets.all_for(conn, "filament") if x["name"] == "Meine PETG-Klasse")
    assert p["data"] == {"brand": "Neuhersteller", "plastic": "PETG", "price": "19.99"}
    assert "Neuhersteller" in catalog.brands(conn, catalog.BY_KEY["filament"])
    client.post(f"/neu/preset/{p['id']}/loeschen", data={"typ": "filament"})
    assert all(x["name"] != "Meine PETG-Klasse" for x in presets.all_for(conn, "filament"))
    assert "Name" in client.post("/neu/preset", data={"typ": "harz", "f_material": "Tough"}).text


def test_resin_has_price_and_presets(client: TestClient) -> None:
    page = client.get("/neu?typ=harz").text
    assert 'id="f_price"' in page and ">Standard<" in page and 'id="f_bottle_weight"' in page


def test_decimal_comma_becomes_point() -> None:
    assert catalog.number("1,75") == "1.75" and catalog.number("0,5 kg") == "0.5 kg"
    assert catalog.number("6, 8, 10") == "6, 8, 10"  # Listen mit Leerzeichen bleiben
    js = (Path(__file__).parents[1] / "app/static/app.js").read_text(encoding="utf-8")
    assert "Dezimalzahlen immer mit Punkt" in js


def test_required_fields_listed_first_then_optional(client: TestClient) -> None:
    client.post("/neu/pflicht", data={"typ": "schraube", "req_length": "1"})
    page = client.get("/neu?typ=schraube").text
    assert page.index("Pflichtfelder") < page.index('id="f_length"') < page.index("Optional")
    assert page.index("Optional") < page.index('id="f_head"')
    assert 'name="keep_head"' in page and "merken</label>" not in page  # kleiner Haken ohne Text


def test_move_bin_by_drag_and_drop(client: TestClient) -> None:
    k = norb(client)
    client.post(f"/n/{k}/bins", data={"position": "A1", "size": "2x1"})
    page = client.get(f"/n/{k}").text
    assert 'id="topview"' in page and 'class="tv-drag"' in page and 'id="tv-move-toggle"' in page
    m = re.search(r'data-bin="(\d+)"', page)
    assert m
    bin_id = m.group(1)
    r = client.post(f"/n/{k}/bins/{bin_id}/move", data={"cells": "C2,D2"})
    assert "nach C2 verschoben" in r.text
    assert 'data-bincells="C2,D2"' in client.get(f"/n/{k}").text
    r = client.post(f"/n/{k}/bins/{bin_id}/move", data={"cells": "C1,D1"})  # Griff-Zellen
    assert "nicht möglich" in r.text
    r = client.post(f"/n/{k}/bins/{bin_id}/move", data={"cells": "C2,C3"})  # falsche Form
    assert "nicht möglich" in r.text


def test_cad_params_and_bins_file(client: TestClient, tmp_path: Path) -> None:
    k = norb(client)
    client.post(f"/n/{k}/bins", data={"position": "B2", "size": "2x1", "div": "3x1"})
    conn = connect(tmp_path / "lager.db")
    bin_id = conn.execute("SELECT id FROM container WHERE kind = 'bin'").fetchone()["id"]
    assert "Druck-Parameter" in client.get(f"/n/{bin_id}").text
    client.post(f"/n/{bin_id}/cad", data={"wall": "1,6", "scoop": "0"})
    data = client.get("/labels/bins.json").json()
    assert data["format"] == "kp-lager-bins/1"
    b = data["boxes"][0]["bins"][0]
    assert b["size"] == "2x1" and b["divisions"] == {"x": 3, "y": 1} and b["cells"] == ["B2", "C2"]
    assert b["params"]["wall"] == 1.6 and b["params"]["scoop"] == 0.0
    assert b["params"]["label"] is False  # Checkbox nicht gesetzt = aus
    assert len(b["compartments"]) == 3 and "norb_bins.py 2x1 --div 3x1" in b["command"]
    assert (tmp_path / "druck" / "bins.json").exists()


def test_bin_label_editor_uses_tags_and_queues_side_label(
    client: TestClient, tmp_path: Path
) -> None:
    k = norb(client)
    client.post(f"/n/{k}/bins", data={"position": "A1", "size": "2x1", "div": "2x1"})
    b = box(client)  # Teil ohne eigenes Etikett (nur Tag) anlegen
    client.post("/neu", data={"typ": "mutter", "f_kind": "Sechskantmutter", "f_thread": "M3",
                              "no_label": "1", "target": str(b)})  # fmt: skip
    conn = connect(tmp_path / "lager.db")
    bin_id = conn.execute("SELECT id FROM container WHERE kind = 'bin'").fetchone()["id"]
    comps = [
        r["id"]
        for r in conn.execute("SELECT id FROM container WHERE parent_id = ? ORDER BY id", (bin_id,))
    ]
    page = client.get(f"/n/{bin_id}/etikett").text
    assert "Sechskantmutter M3" in page and 'class="chip tag-chip"' in page
    assert client.get(f"/n/{bin_id}/etikett.png").content[:4] == b"\x89PNG"
    r = client.post(f"/n/{bin_id}/etikett", data={f"t_{comps[0]}": "Sechskantmutter M3\nM3x10",
                                                  f"t_{comps[1]}": "Dübel 6", "queue": "1",
                                                  "color": "red"})  # fmt: skip
    assert "A4-Warteschlange" in r.text
    job = a4.queue(conn)[0]["job"]
    assert job["type"] == "bin_side" and job["color"] == "red"
    assert (job["cols"], job["rows"]) == (2, 1)
    assert job["cells"][0]["lines"] == ["Sechskantmutter M3", "M3x10"]
    first = kasten.print_file(conn)["boxes"][0]["bins"][0]["compartments"][0]
    assert first["label"].startswith("Sechs")
