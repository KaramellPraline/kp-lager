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
