"""Bedienung: Matrix mit Zuletzt-vorn, Filament/Harz-Auswahllisten, Box-Größe + Airtight,
Maschinen/Trockner mit Etikett, Scan-Ablauf „Trockner → Filament = getrocknet“, Inhaltsvorschau."""

from fastapi.testclient import TestClient


def _box(c: TestClient, name: str = "Kiste", kind: str = "box", **extra: str) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": kind, **extra})
    return int(r.url.path.rsplit("/", 1)[1])


def _items(c: TestClient, box: int) -> list[dict]:  # type: ignore[type-arg]
    return list(c.get(f"/api/v1/containers/{box}").json()["items"])


def test_recent_categories_and_kinds_come_first(client: TestClient) -> None:
    box = _box(client, "Regal", "toolbox")
    client.post("/quickadd", data={"mode": "item", "cat": "CMP", "target": box, "text": "ESP32"})
    page = client.get("/").text
    cats = page.split('aria-label="Kategorie"')[1].split("</div>")[0]
    assert cats.index('value="CMP"') < cats.index('value="ART"')
    tiles = page.split('aria-label="Art des Behälters"')[1].split("</div>")[0]
    assert tiles.index('value="toolbox"') < tiles.index('value="box"')
    assert 'value="toolbox" checked' in tiles  # zuletzt verwendet = vorbelegt


def test_filament_and_resin_dropdown_creation(client: TestClient) -> None:
    box = _box(client)
    r = client.post("/quickadd", data={
        "mode": "item", "cat": "FIL", "target": box, "text": "", "count": "3",
        "spec_brand": "neu", "spec_brand_new": "Sunlu", "spec_material": "PETG",
        "spec_color": "Weiß", "spec_diameter": "1.75", "spec_weight": "1000"})  # fmt: skip
    assert "Sunlu PETG Weiß" in r.text
    item = _items(client, box)[0]
    assert item["qty"] == 3 and item["code"].startswith("FIL-")
    sheet = client.get(f"/items/{item['id']}").text
    assert "Sunlu" in sheet and "1.75" in sheet
    client.post("/quickadd", data={"mode": "item", "cat": "RES", "target": box, "text": "",
                                   "spec_material": "ABS-like", "spec_color": "Grau"})  # fmt: skip
    assert any(i["name"] == "ABS-like Grau" for i in _items(client, box))
    page = client.get("/").text  # Gelerntes steht jetzt in den Listen, vorn
    brands = page.split('name="spec_brand"')[1].split("</select>")[0]
    assert brands.index("<option>Sunlu") < brands.index("<option>Prusament")


def test_box_size_from_existing_and_airtight(client: TestClient) -> None:
    first = _box(client, "Dose A", "box", dims_other="200x150x100", airtight="1")
    assert ">Luftdicht<" in client.get(f"/n/{first}").text
    assert "200 × 150 × 100 mm" in client.get(f"/n/{first}").text
    page = client.get("/").text
    assert "200x150x100" in page.split("data-opts=")[1].split(">")[0]  # bereits vorhandene Größe
    second = _box(client, "Dose B", "box", dims="200x150x100")
    assert ">Luftdicht<" not in client.get(f"/n/{second}").text


def test_machine_and_dryer_get_labels(client: TestClient) -> None:
    m = _box(client, "Prusa MK4", "machine")
    page = client.get(f"/n/{m}").text
    assert "MAS-001" in page
    assert "MAS-001" in client.get("/labels").text  # Etikett wartet in der Schlange
    d = _box(client, "Trockner 1", "dryer")
    assert "TRO-001" in client.get(f"/n/{d}").text


def test_scan_dryer_then_filament_marks_dried(client: TestClient) -> None:
    d = _box(client, "Trockner 1", "dryer")
    box = _box(client)
    client.post("/quickadd", data={"mode": "item", "cat": "FIL", "target": box, "text": "",
                                   "spec_material": "PETG", "spec_color": "Weiß"})  # fmt: skip
    fil = _items(client, box)[0]
    # ohne Trockner-Scan: normales Verhalten
    plain = client.get(f"/c/{fil['code']}")
    assert plain.url.path == f"/items/{fil['id']}"
    # Trockner scannen → wartet auf Filament
    wait = client.get("/c/TRO-001")
    assert wait.url.path == f"/trockner/scan/{d}" and "bereit" in wait.text
    done = client.get(f"/c/{fil['code']}")
    assert "als getrocknet gespeichert" in done.text and done.url.path == f"/trockner/scan/{d}"
    page = client.get(f"/items/{fil['id']}").text
    assert "per Scan" not in page and "PETG" in page and "fertig" in page
    # noch eine Spule im selben Trockner möglich, dann beenden
    client.post(f"/trockner/scan/{d}/ende")
    after = client.get(f"/c/{fil['code']}")
    assert after.url.path == f"/items/{fil['id']}"
    # Nicht-Filament bleibt normal
    client.get("/c/TRO-001")
    client.post("/quickadd", data={"mode": "item", "cat": "ART", "target": box, "text": "Zange"})
    art = next(i for i in _items(client, box) if i["name"] == "Zange")
    assert client.get(f"/c/{art['code']}").url.path == f"/items/{art['id']}"


def test_peek_and_collapse_marker(client: TestClient) -> None:
    box = _box(client)
    for n in range(12):
        client.post(
            "/quickadd", data={"mode": "item", "cat": "ART", "target": box, "text": f"T{n}"}
        )
    peek = client.get(f"/n/{box}/inhalt").text
    assert peek.count("<li>") == 12 and 'data-collapse="9"' in peek
    assert 'data-collapse="9"' in client.get(f"/n/{box}").text
    assert 'id="qa-peek"' in client.get("/").text
