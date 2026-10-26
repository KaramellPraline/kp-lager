import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import repo
from app.db import connect


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = connect(":memory:")
    keller = repo.create_container(c, "Keller", "raum")
    box = repo.create_container(c, "Werkstatt", "eurobox", parent_id=keller, code="0042")
    kasten = repo.create_container(c, "Kleinteile", "sortierkasten", parent_id=keller, grid="2x2")
    fach = repo.children(c, kasten)[2]["id"]
    repo.add_item(c, fach, "Holzschrauben 4x40", qty_hint="viele", tags="befestigung holz")
    repo.add_item(c, box, "Lötzinn", qty=2, tags="löten elektronik")
    repo.add_item(c, box, "Ölkännchen", notes="für Fahrradkette")
    repo.add_item(c, box, "M3 Muttern", qty=50)
    yield c
    c.close()


def names(rows: list[dict[str, object]]) -> list[object]:
    return [r["name"] for r in rows]


def test_partial_word_in_compound(conn: sqlite3.Connection) -> None:
    hits = repo.search(conn, "schraub")
    assert names(hits) == ["Holzschrauben 4x40"]
    assert hits[0]["path"] == "Keller › Kleinteile › Fach B1"


def test_case_and_umlauts(conn: sqlite3.Connection) -> None:
    assert names(repo.search(conn, "LÖTZINN")) == ["Lötzinn"]
    assert names(repo.search(conn, "öl")) == ["Ölkännchen"]  # kurz -> LIKE mit fold()


def test_tags_notes_and_multiple_terms(conn: sqlite3.Connection) -> None:
    assert names(repo.search(conn, "elektronik")) == ["Lötzinn"]
    assert names(repo.search(conn, "fahrrad")) == ["Ölkännchen"]
    assert names(repo.search(conn, "holz befestigung")) == ["Holzschrauben 4x40"]
    assert repo.search(conn, "holz löten") == []


def test_short_terms_and_quotes(conn: sqlite3.Connection) -> None:
    assert names(repo.search(conn, "M3")) == ["M3 Muttern"]
    assert repo.search(conn, '"') == []


def test_index_follows_updates_and_deletes(conn: sqlite3.Connection) -> None:
    item = repo.search(conn, "muttern")[0]["id"]
    assert isinstance(item, int)
    repo.update_item(conn, item, name="M3 Sechskantmuttern")
    assert names(repo.search(conn, "sechskant")) == ["M3 Sechskantmuttern"]
    repo.delete_item(conn, item)
    assert repo.search(conn, "sechskant") == []


def test_containers_by_name_and_code(conn: sqlite3.Connection) -> None:
    assert names(repo.search_containers(conn, "werk")) == ["Werkstatt"]
    assert names(repo.search_containers(conn, "0042")) == ["Werkstatt"]
    assert repo.search_containers(conn, "Fach") == []  # Standard-Fächer nicht als Treffer


def test_search_page(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Box", "kind": "kiste", "code": "0007"})
    box = r.url.path.rsplit("/", 1)[1]
    client.post(f"/n/{box}/items", data={"name": "Akkuschrauber", "qty": "1"})
    r = client.get("/suche", params={"q": "schrauber"})
    assert "Akkuschrauber" in r.text and "Box" in r.text
    assert client.get("/suche", params={"q": "0007"}).url.path == f"/n/{box}"
    assert "Nichts gefunden" in client.get("/suche", params={"q": "xyz"}).text
