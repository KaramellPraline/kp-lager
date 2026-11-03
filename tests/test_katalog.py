"""Katalog (/neu), Einsatz-Assistent (/neu/bin) und Baumansicht."""

from fastapi.testclient import TestClient

from app import catalog


def _box(c: TestClient, name: str = "Kiste", kind: str = "box") -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": kind})
    return int(r.url.path.rsplit("/", 1)[1])


def _items(c: TestClient, box: int) -> list[dict]:  # type: ignore[type-arg]
    return list(c.get(f"/api/v1/containers/{box}").json()["items"])


def test_names_follow_templates() -> None:
    t = catalog.BY_KEY["schraube"]
    assert catalog.name(t, {"head": "Zylinderkopfschraube", "thread": "M3", "length": "10"}) == (
        "Zylinderkopfschraube M3x10"
    )
    assert catalog.name(t, {"head": "Madenschraube", "thread": "M4"}) == "Madenschraube M4"
    assert catalog.name(catalog.BY_KEY["insert"], {"kind": "Holzinsert", "thread": "M4"}) == (
        "Holzinsert M4"
    )
    assert catalog.name(catalog.BY_KEY["anzeige"], {"kind": "OLED 0.96"}) == "OLED 0.96"
    assert catalog.name(t, {}) == ""


def test_every_type_is_usable() -> None:
    assert len({t.key for t in catalog.TYPES}) == len(catalog.TYPES)
    for t in catalog.TYPES:
        values = {f.key: (f.options[0] if f.options else "X") for f in t.fields}
        assert catalog.name(t, values), t.key


def test_catalog_page_and_create_resets_form(client: TestClient) -> None:
    page = client.get("/neu?typ=schraube").text
    assert "Zylinderkopfschraube" in page and "Einsatz in Sortierkasten" in page
    assert 'id="type-filter"' in page and "Elektronik" in page
    box = _box(client)
    r = client.post("/neu", data={"typ": "schraube", "f_head": "Zylinderkopfschraube",
                                  "f_thread": "M3", "f_length": "10", "qty": "50",
                                  "target": box, "f_finish": "Schwarz 12.9"})  # fmt: skip
    assert "Zylinderkopfschraube M3x10" in r.text
    assert r.url.path == "/neu" and r.url.params["typ"] == "schraube"  # gleicher Typ, leer
    assert 'name="f_thread" list="dl_thread" placeholder="" autocomplete="off"' in r.text
    assert 'name="f_thread" value=' not in r.text  # Feld leer
    item = _items(client, box)[0]
    assert item["name"] == "Zylinderkopfschraube M3x10" and item["qty"] == 50
    assert item["code"].startswith("CNS-")
    assert f'value="{box}" selected' in r.text  # Ziel bleibt


def test_electronics_get_datasheet_profile(client: TestClient) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "sensor", "f_kind": "Temperatur / Feuchte",
                              "f_model": "DHT22", "f_interface": "Digital", "target": box})  # fmt: skip
    item = _items(client, box)[0]
    assert item["name"] == "DHT22 Temperatur / Feuchte" and item["code"].startswith("CMP-")
    sheet = client.get(f"/items/{item['id']}").text
    assert "Sensor" in sheet and "Digital" in sheet


def test_empty_form_is_rejected(client: TestClient) -> None:
    r = client.post("/neu", data={"typ": "schraube"}, headers={"referer": "http://t/neu"})
    assert "mindestens ein Feld" in r.text


def test_preview_endpoint(client: TestClient) -> None:
    r = client.get("/neu/vorschau", params={"typ": "schraube", "f_head": "Senkkopfschraube",
                                            "f_thread": "M3", "f_length": "6"})  # fmt: skip
    assert r.json()["name"] == "Senkkopfschraube M3x6"


def test_bin_assistant_creates_bin_with_contents(client: TestClient) -> None:
    r0 = client.post("/containers", data={"name": "Schraubenkasten", "kind": "sortingbox",
                                          "model": "norb16"})  # fmt: skip
    kid = int(r0.url.path.rsplit("/", 1)[1])
    page = client.get("/neu/bin").text
    assert "Schraubenkasten" in page and "Fächer im Einsatz" in page
    r = client.post("/neu/bin", data={
        "kasten": kid, "pos": "A1", "x": "1", "y": "1", "div": "3x1", "content": "1", "queue": "1",
        "r0_typ": "schraube|Zylinderkopfschraube", "r0_var": "M3x10", "r0_qty": "100",
        "r1_typ": "insert|Holzinsert", "r1_var": "M4", "r1_qty": "",
    })  # fmt: skip
    assert "angelegt, 2 Teile" in r.text
    assert r.url.path == "/neu/bin" and f"kasten_id={kid}" in str(r.url)
    tree = client.get(f"/n/{kid}/zweig").text
    assert "BIN-001" in tree or "Einsatz A1" in tree
    # nächster Einsatz: A1 ist belegt, Assistent bietet andere Zelle an
    assert "data-info=" in client.get(f"/neu/bin?kasten_id={kid}").text


def test_tree_and_home(client: TestClient) -> None:
    room = _box(client, "Werkstatt", "room")
    shelf = int(client.post("/quickadd", data={"mode": "container", "text": "Regal 1",
                                               "kind": "shelf", "target": room}).url.path.rsplit("/", 1)[1])  # fmt: skip
    client.post("/neu", data={"typ": "kleber", "f_kind": "Sekundenkleber", "target": shelf})
    home = client.get("/").text
    assert 'class="card tree-root"' in home and "Werkstatt" in home
    assert f'data-src="/n/{room}/zweig"' in home
    branch = client.get(f"/n/{room}/zweig").text
    assert "Regal 1" in branch and f"/n/{shelf}/zweig" in branch
    leaf = client.get(f"/n/{shelf}/zweig").text
    assert "Sekundenkleber" in leaf
    assert "Übersicht" in client.get("/baum").text and "Werkstatt" in client.get("/baum").text
    assert 'href="/neu"' in home
