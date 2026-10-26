import re

from fastapi.testclient import TestClient


def node_id(r: object) -> int:
    m = re.search(r"/n/(\d+)$", str(r.url))  # type: ignore[attr-defined]
    assert m, r.url  # type: ignore[attr-defined]
    return int(m.group(1))


def make(client: TestClient, **form: str) -> int:
    r = client.post("/containers", data=form)
    assert r.status_code == 200
    return node_id(r)


def test_unknown_code_offers_creation_then_redirects(client: TestClient) -> None:
    r = client.get("/c/EUR-042")
    assert "Etikett EUR-042 ist noch frei" in r.text
    keller = make(client, name="Keller", kind="raum")
    box = make(client, name="Elektronik", kind="eurobox", code="EUR-042", parent_id=str(keller))
    r = client.get("/c/EUR-042")
    assert node_id(r) == box
    assert "Keller" in r.text and "Elektronik" in r.text


def test_add_take_put_item(client: TestClient) -> None:
    box = make(client, name="Box", kind="eurobox")
    r = client.post(f"/n/{box}/items", data={"name": "Lötzinn", "qty": "2"})
    assert "„Lötzinn“ eingelagert" in r.text
    item = int(re.search(r'id="item-(\d+)"', r.text).group(1))  # type: ignore[union-attr]
    r = client.post(f"/items/{item}/qty", data={"delta": "-1"})
    assert '<span class="qty ">1' in r.text
    r = client.post(f"/items/{item}/qty", data={"delta": "-1"})
    assert "disabled" in r.text  # Minus-Knopf bei 0 aus
    r = client.post(f"/items/{item}/qty", data={"delta": "-1"}, headers={"referer": f"/n/{box}"})
    assert "Nur 0 vorhanden" in r.text


def test_invalid_qty_shows_message(client: TestClient) -> None:
    box = make(client, name="Box", kind="eurobox")
    r = client.post(
        f"/n/{box}/items", data={"name": "X", "qty": "drei"}, headers={"referer": f"/n/{box}"}
    )
    assert "keine ganze Zahl" in r.text


def test_sortierkasten_shows_grid(client: TestClient) -> None:
    kasten = make(client, name="Schrauben", kind="sortierkasten", grid="3x2")
    r = client.get(f"/n/{kasten}")
    assert "Fächer" in r.text and "grid-template-columns: repeat(3" in r.text
    assert r.text.count('class="cell') == 6


def test_carry_item_and_drop(client: TestClient) -> None:
    a = make(client, name="Box A", kind="eurobox")
    b = make(client, name="Box B", kind="eurobox")
    client.post(f"/n/{a}/items", data={"name": "Multimeter", "qty": "1"})
    item = int(re.search(r'id="item-(\d+)"', client.get(f"/n/{a}").text).group(1))  # type: ignore[union-attr]
    r = client.post(f"/carry/item/{item}")
    assert "Unterwegs: <b>Multimeter</b>" in r.text
    r = client.get(f"/n/{b}")
    assert f'action="/drop/{b}"' in r.text
    r = client.post(f"/drop/{b}")
    assert "„Multimeter“ abgelegt" in r.text and "Unterwegs" not in r.text
    assert "Multimeter" not in client.get(f"/n/{a}").text


def test_carry_container_into_itself_rejected(client: TestClient) -> None:
    keller = make(client, name="Keller", kind="raum")
    box = make(client, name="Box", kind="kiste", parent_id=str(keller))
    client.post(f"/carry/node/{keller}")
    r = client.post(f"/drop/{box}", headers={"referer": f"/n/{box}"})
    assert "nicht in sich selbst" in r.text


def test_duplicate_code_message(client: TestClient) -> None:
    make(client, name="A", kind="kiste", code="KIS-001")
    r = client.post(
        "/containers",
        data={"name": "B", "kind": "kiste", "code": "KIS-001"},
        headers={"referer": "/"},
    )
    assert "Code ist schon vergeben" in r.text


def test_delete_only_empty(client: TestClient) -> None:
    box = make(client, name="Box", kind="kiste")
    client.post(f"/n/{box}/items", data={"name": "X"})
    r = client.post(f"/n/{box}/delete", headers={"referer": f"/n/{box}"})
    assert "nicht leer" in r.text
    kasten = make(client, name="Kasten", kind="sortierkasten", grid="2x2")
    r = client.post(f"/n/{kasten}/delete")
    assert "Behälter gelöscht" in r.text
