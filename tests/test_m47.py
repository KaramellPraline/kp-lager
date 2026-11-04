"""M47: Layout-Vorlagen, Druckmodus, Leergewicht, Raster-Modelle."""

from fastapi.testclient import TestClient

from app import kasten, labels


def _box(c: TestClient) -> int:
    r = c.post("/containers", data={"name": "Regal", "kind": "toolbox"}, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def test_layout_presets_and_apply_to_all(client: TestClient) -> None:
    assert "alles" in labels.PRESETS
    page = client.get("/etiketten/typ/schraube").text
    assert 'class="chip preset"' in page and "Alles (Name" in page
    form = {"qr": "left", "t_0": "{name}", "w_0": "3", "a_0": "left", "all": "1"}
    client.post("/etiketten/typ/schraube", data=form)
    assert "eigenes Layout" in client.get("/etiketten/typ").text


def test_print_mode_menu_and_queue(client: TestClient) -> None:
    assert "Druck: Aus" in client.get("/neu").text
    client.post("/neu/druckmodus", data={"mode": "sammel"})
    assert "Druck: Sammeln" in client.get("/neu").text
    box = _box(client)
    client.post("/neu", data={"typ": "schraube", "f_thread": "M3", "f_length": "10",
                              "target": str(box)})  # fmt: skip
    assert "M3" in client.get("/labels").text  # liegt in der Warteschlange


def test_container_tare(client: TestClient) -> None:
    box = _box(client)
    client.post(f"/n/{box}/edit", data={"name": "Regal", "tare": "125,5"})
    assert 'name="tare" inputmode="decimal" value="125.5"' in client.get(f"/n/{box}").text
    r = client.post(f"/n/{box}/edit", data={"name": "Regal", "tare": "abc"})
    assert "kein Gewicht" in r.text


def test_raster_models() -> None:
    assert len(kasten.MODELS) >= 18
    assert kasten.MODELS["raster3x4"].cols == 3


def test_card_kinds_and_catalog_note(client: TestClient) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "schraube", "f_thread": "M3", "f_length": "10",
                              "target": str(box), "note": "https://example.org/db.pdf"})  # fmt: skip
    iid = client.get(f"/api/v1/containers/{box}").json()["items"][0]["id"]
    page = client.get(f"/items/{iid}").text
    assert 'href="https://example.org/db.pdf"' in page
    client.post(f"/items/{iid}/cards", data={"kind": "checklist", "title": "T",
                                             "body": "[x] eins\n[ ] zwei"})  # fmt: skip
    client.post(f"/items/{iid}/cards", data={"kind": "spec", "title": "D", "body": "U; 3,3 V"})
    page = client.get(f"/items/{iid}").text
    assert "[x] eins" in page and "[ ] zwei" in page and "3,3 V" in page


def test_admin_numbers_grouped(client: TestClient) -> None:
    page = client.get("/settings/admin").text
    assert 'id="nummern"' in page and 'id="counter-filter"' in page and "nächster" in page


def test_material_types_in_catalog(client: TestClient) -> None:
    page = client.get("/neu").text
    assert "/neu/material" not in page and 'data-g="Filament &amp; Harz"' in page
    box = _box(client)
    client.post("/neu", data={"typ": "filament", "f_brand": "Sunlu", "f_material": "PETG",
                              "f_color": "Weiß", "f_weight": "1", "target": str(box)})  # fmt: skip
    client.post("/neu", data={"typ": "harz", "f_brand": "Elegoo", "f_material": "Standard",
                              "f_color": "Grau", "f_volume": "500", "target": str(box)})  # fmt: skip
    client.post("/neu", data={"typ": "norb16_bin", "f_size": "2x1", "f_state": "nicht gedruckt",
                              "target": str(box)})  # fmt: skip
    names = [i["name"] for i in client.get(f"/api/v1/containers/{box}").json()["items"]]
    assert "Sunlu PETG Weiß" in names and "Elegoo Standard Grau 500ml" in names
    assert "Norb16 Bin 2x1 (nicht gedruckt)" in names
    codes = [i["code"] for i in client.get(f"/api/v1/containers/{box}").json()["items"]]
    assert any(c.startswith("FIL-") for c in codes) and any(c.startswith("RES-") for c in codes)


def test_einsatz_menu_presets_and_unprinted(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Kasten", "kind": "sortingbox",
                                         "model": "norb16"}, follow_redirects=False)  # fmt: skip
    kid = int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])
    assert 'data-bin-size="2x2"' in client.get("/neu/bin").text
    r = client.post("/neu/bin", data={"kasten": str(kid), "pos": "A1", "x": "2", "y": "1",
                                      "div": "1x1", "unprinted": "1"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    page = client.get(f"/n/{kid}").text
    assert "noch nicht gedruckt" in page or "Einsatz" in page
