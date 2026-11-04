"""M53: Einsätze (BIN) mit Rastermaß und Teilung unter Hinzufügen › Behälter anlegen, im Sortierkasten wählbar."""

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import kasten
from app.db import connect


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def norb(client: TestClient) -> str:
    r = client.post("/containers", data={"name": "Kleinteile", "kind": "sortierkasten",
                                          "code": "SOR-001", "model": "norb16"})  # fmt: skip
    return node_of(r)


def make_bin(
    client: TestClient, tmp_path: Path, size: str = "2x1", grid: str = "3x1", name: str = ""
) -> str:
    client.post("/containers", data={"kind": "bin", "name": name, "size": size, "grid": grid})
    row = (
        connect(tmp_path / "lager.db")
        .execute("SELECT MAX(id) FROM container WHERE kind = 'bin'")
        .fetchone()
    )
    return str(row[0])


def test_add_page_offers_bin_with_size_and_division(client: TestClient) -> None:
    page = client.get("/neu/behaelter?art=bin").text
    assert "Rastermaß" in page and "Teilung" in page and 'name="size"' in page
    assert "/neu/behaelter?art=bin" in client.get("/neu/behaelter").text  # Art in der Liste


def test_create_bin_with_size_division_and_code(client: TestClient, tmp_path: Path) -> None:
    bid = make_bin(client, tmp_path)
    conn = connect(tmp_path / "lager.db")
    b = conn.execute("SELECT * FROM container WHERE id = ?", (bid,)).fetchone()
    assert b["kind"] == "bin" and b["size"] == "2x1" and b["grid"] == "3x1"
    assert b["code"].startswith("BIN-") and b["name"] == "Einsatz 2x1 · 3x1"  # Name aus den Maßen
    assert (
        conn.execute("SELECT COUNT(*) FROM container WHERE parent_id = ?", (bid,)).fetchone()[0]
        == 3
    )
    own = make_bin(client, tmp_path, "1x1", "1x1", "Schrauben")  # eigener Name, keine Teilung
    row = conn.execute("SELECT * FROM container WHERE id = ?", (own,)).fetchone()
    assert row["name"] == "Schrauben" and row["grid"] is None and row["size"] == "1x1"
    client.post("/containers", data={"kind": "bin", "size": "1x1", "size_custom": "3x2",
                                     "grid_custom": "4x2"})  # fmt: skip
    c2 = conn.execute(
        "SELECT * FROM container WHERE id = (SELECT MAX(id) FROM container WHERE kind = 'bin')"
    ).fetchone()
    assert c2["size"] == "3x2" and c2["grid"] == "4x2"


def test_invalid_size_is_rejected(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/containers", data={"kind": "bin", "name": "X", "size": "abc"})
    assert "ungültig" in r.text
    conn = connect(tmp_path / "lager.db")
    assert conn.execute("SELECT COUNT(*) FROM container WHERE kind = 'bin'").fetchone()[0] == 0


def test_box_page_lists_loose_bin_and_places_it(client: TestClient, tmp_path: Path) -> None:
    k = norb(client)
    bid = make_bin(client, tmp_path)
    page = client.get(f"/n/{k}").text
    assert "Vorhandenen Einsatz wählen" in page and f'value="{bid}"' in page
    r = client.post(f"/n/{k}/bins/existing", data={"bin_id": bid, "position": "A1"})
    assert "eingesetzt" in r.text and "bei A1" in r.text
    conn = connect(tmp_path / "lager.db")
    b = conn.execute("SELECT * FROM container WHERE id = ?", (bid,)).fetchone()
    assert str(b["parent_id"]) == k and b["position"] == "A1" and b["name"] == "Einsatz A1"
    assert {"A1", "B1"} <= set(kasten.occupied(conn, int(k)))  # 2x1 = zwei Zeilen
    assert "Vorhandenen Einsatz wählen" not in client.get(f"/n/{k}").text  # nicht mehr lose
    again = client.post(f"/n/{k}/bins/existing", data={"bin_id": bid, "position": "A3"})
    assert "schon in einem Sortierkasten" in again.text


def test_existing_bin_respects_handle_and_occupied_cells(
    client: TestClient, tmp_path: Path
) -> None:
    k = norb(client)
    first = make_bin(client, tmp_path)
    second = make_bin(client, tmp_path)
    r = client.post(f"/n/{k}/bins/existing", data={"bin_id": first, "position": "B1"})
    assert "Griff" in r.text  # 2x1 ab B1 reicht in C1 (Griff)
    client.post(f"/n/{k}/bins/existing", data={"bin_id": first, "position": "A1"})
    r = client.post(f"/n/{k}/bins/existing", data={"bin_id": second, "position": "A1"})
    assert "belegt" in r.text
    r = client.post(f"/n/{k}/bins/existing", data={"bin_id": second, "position": "A2"})
    assert "eingesetzt" in r.text
