import re

from fastapi.testclient import TestClient

from app import codes


def _box(client: TestClient) -> int:
    r = client.post(
        "/quickadd", data={"mode": "container", "text": "Druckerregal", "kind": "shelf"}
    )
    return int(r.url.path.rsplit("/", 1)[1])


def test_fil_res_in_schema_and_new_spool_by_scan(client: TestClient) -> None:
    assert codes.normalize("fil7") == "FIL-007" and codes.normalize("res1") == "RES-001"
    page = client.get("/codes").text
    assert "<b>FIL</b>-001 · Filament" in page and "<b>RES</b>-001 · UV-Harz" in page
    new = client.get("/C/FIL-003").text
    assert "Neue Filament-Spule" in new
    box = _box(client)
    r = client.post(
        "/items/new", data={"code": "FIL-003", "container_id": box, "name": "PETG schwarz"}
    )
    assert "Eigenschaften bearbeiten" in r.text and "Max. Volumenfluss" in r.text
    item_id = int(r.url.path.rsplit("/", 1)[1])
    r = client.post(f"/items/{item_id}/specs", data={
        "material": "fil", "spec_material": "PETG", "spec_weight": "1000", "spec_nozzle_min": "230",
        "spec_nozzle_max": "250", "spec_flow_max": "15", "spec_tensile": "50"})  # fmt: skip
    assert (
        "Max. Volumenfluss</dt><dd>15 mm³/s" in r.text and "Zugfestigkeit</dt><dd>50 MPa" in r.text
    )
    r = client.post(f"/items/{item_id}/edit", data={
        "name": "PETG schwarz", "material": "fil", "price": "21,90",
        "order_url": "https://shop.example/petg"})  # fmt: skip
    assert "21,90 €" in r.text and "21,90 €/kg" in r.text and "https://shop.example/petg" in r.text
    assert "230" in r.text  # Eigenschaften bleiben beim Bearbeiten erhalten
    overview = client.get("/material").text
    assert "PETG schwarz" in overview and "230–250 °C" in overview and "15 mm³/s" in overview
    # neuer Code für ein Material-Teil bekommt das Material-Präfix
    r = client.post("/quickadd", data={"mode": "item", "text": "Resin grau", "target": box})
    rid = int(re.findall(r'href="/items/(\d+)"', client.get(f"/n/{box}").text)[-1])
    client.post(f"/items/{rid}/code", data={"remove": "1"})
    client.post(f"/items/{rid}/edit", data={"name": "Resin grau", "material": "res"})
    assert "RES-001" in client.post(f"/items/{rid}/code").text


def test_item_prefix_not_for_containers_and_bad_price(client: TestClient) -> None:
    box = _box(client)
    r = client.post(f"/n/{box}/edit", data={"name": "Druckerregal", "code": "FIL-001"})
    assert "FIL-Codes sind für Teile" in r.text
    item = client.post("/quickadd", data={"mode": "item", "text": "Düse", "target": box})
    iid = int(re.findall(r'href="/items/(\d+)"', client.get(f"/n/{box}").text)[-1])
    assert (
        "keine Zahl"
        in client.post(f"/items/{iid}/edit", data={"name": "Düse", "price": "billig"}).text
    )
    assert item.status_code == 200
