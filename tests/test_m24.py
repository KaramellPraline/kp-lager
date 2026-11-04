import re

from fastapi.testclient import TestClient


def _shelf(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Regal", "kind": "shelf"})
    return int(r.url.path.rsplit("/", 1)[1])


def _item(c: TestClient, shelf: int, text: str, cat: str) -> int:
    c.post("/quickadd", data={"mode": "item", "text": text, "target": shelf, "cat": cat})
    items = c.get(f"/api/v1/containers/{shelf}").json()["items"]
    return int(next(i["id"] for i in items if i["name"] in text))


def test_weigh_filament_and_resin(client: TestClient) -> None:
    shelf = _shelf(client)
    fil = _item(client, shelf, "PLA weiß", "FIL")
    client.post(f"/items/{fil}/specs", data={"material": "fil", "spec_weight": "1000",
                                            "spec_spool_weight": "200", "spec_density": "1.24"})  # fmt: skip
    r = client.post(f"/items/{fil}/weigh", data={"gross": "840"})
    assert "Rest: 640 g ≈ 215 m" in r.text and "64 %" in r.text
    r = client.post(f"/items/{fil}/weigh", data={"gross": "300"})
    assert "fast leer" in r.text and "Einkaufsliste" in r.text
    assert "PLA weiß" in client.get("/einkauf").text
    res = _item(client, shelf, "Resin grau", "RES")
    r = client.post(f"/items/{res}/weigh", data={"gross": "620"})
    assert "Leergewicht 120 g angenommen" in r.text and "≈ 455 ml" in r.text
    assert "Rest" in client.get("/material").text
    assert "nur für Filament" in client.post(f"/items/{_item(client, shelf, 'Zange', 'ART')}/weigh",
                                             data={"gross": "5"}).text  # fmt: skip


def test_content_labels_for_bins_and_compartments(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Kleinteile", "kind": "sortingbox",
                                          "code": "SOR-001", "model": "norb16"})  # fmt: skip
    k = int(r.url.path.rsplit("/", 1)[1])
    client.post(f"/n/{k}/bins", data={"position": "A1", "size": "1x1"})
    page = client.get(f"/n/{k}").text
    target = re.findall(r'<option value="(\d+)">A1', page)[0]
    client.post(f"/n/{k}/quickadd", data={"target": target, "text": "M3 Muttern", "queue": "1"})
    labels_page = client.get("/labels").text
    assert (
        "Inhaltsetiketten vorgemerkt (1)" in labels_page and "BIN-001 · M3 Muttern" in labels_page
    )
    a4 = client.post("/labels/content/a4q")
    assert a4.url.path == "/a4" and "BIN-001" in a4.text
    assert "Inhaltsetiketten vorgemerkt" not in client.get("/labels").text  # nach Übergabe geleert
    bin_id = target
    r = client.post(f"/labels/content/node/{bin_id}")
    assert "vorgemerkt" in r.text
