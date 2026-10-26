import sqlite3
from collections.abc import Iterator

import pytest

from app import repo
from app.db import MIGRATIONS_DIR, connect, migrate
from app.repo import LagerError


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def lager(conn: sqlite3.Connection) -> dict[str, int]:
    keller = repo.create_container(conn, "Keller", "raum")
    regal = repo.create_container(conn, "Regal 1", "regal", parent_id=keller)
    box = repo.create_container(conn, "Elektronik", "eurobox", parent_id=regal, code="0042")
    kasten = repo.create_container(
        conn, "Schrauben", "sortierkasten", parent_id=regal, code="0043", grid="4x3"
    )
    return {"keller": keller, "regal": regal, "box": box, "kasten": kasten}


def test_migrate_is_idempotent(conn: sqlite3.Connection) -> None:
    latest = len(list(MIGRATIONS_DIR.glob("*.sql")))
    assert migrate(conn) == latest
    assert migrate(conn) == latest


def test_path_from_root(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    assert repo.path_label(conn, lager["box"]) == "Keller › Regal 1 › Elektronik"
    assert repo.get_container_by_code(conn, "0042")["id"] == lager["box"]


def test_grid_creates_compartments(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    faecher = repo.children(conn, lager["kasten"])
    assert [f["position"] for f in faecher][:5] == ["A1", "A2", "A3", "A4", "B1"]
    assert len(faecher) == 12
    b3 = next(f for f in faecher if f["position"] == "B3")
    assert repo.path_label(conn, b3["id"]).endswith("Schrauben › Fach B3")


@pytest.mark.parametrize("grid", ["6", "0x3", "axb", "31x2"])
def test_invalid_grid(conn: sqlite3.Connection, grid: str) -> None:
    with pytest.raises(LagerError):
        repo.create_container(conn, "X", "sortierkasten", grid=grid)


def test_duplicate_code_rejected(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_container(conn, "Andere", "kiste", code="0042")


def test_unknown_kind(conn: sqlite3.Connection) -> None:
    with pytest.raises(LagerError):
        repo.create_container(conn, "X", "schrank")


def test_move_container_and_prevent_cycle(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    stapel = repo.create_container(conn, "Kistenberg", "stapel", parent_id=lager["keller"])
    repo.move_container(conn, lager["box"], stapel)
    assert repo.path_label(conn, lager["box"]) == "Keller › Kistenberg › Elektronik"
    with pytest.raises(LagerError):
        repo.move_container(conn, lager["keller"], lager["box"])
    with pytest.raises(LagerError):
        repo.move_container(conn, lager["box"], lager["box"])


def test_take_and_put_with_history(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    item = repo.add_item(conn, lager["box"], "Lötzinn", qty=3, unit="Rolle", tags="löten")
    assert repo.change_qty(conn, item, -2) == 1
    assert repo.change_qty(conn, item, +4) == 5
    with pytest.raises(LagerError):
        repo.change_qty(conn, item, -6)
    assert repo.get_item(conn, item)["qty"] == 5
    assert [e["action"] for e in repo.history(conn, item)] == ["put", "take", "add"]


def test_uncounted_item_only_logs(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    item = repo.add_item(conn, lager["box"], "Kabelbinder", qty_hint="viele")
    assert repo.change_qty(conn, item, -1) is None
    assert repo.history(conn, item)[0]["action"] == "take"


def test_negative_qty_rejected(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    with pytest.raises(LagerError):
        repo.add_item(conn, lager["box"], "X", qty=-1)


def test_move_item_into_compartment(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    b3 = next(f for f in repo.children(conn, lager["kasten"]) if f["position"] == "B3")
    item = repo.add_item(conn, lager["box"], "Holzschrauben 4x40", qty_hint="viele")
    repo.move_item(conn, item, b3["id"])
    assert [i["name"] for i in repo.items_in(conn, b3["id"])] == ["Holzschrauben 4x40"]
    assert repo.items_in(conn, lager["box"]) == []


def test_container_with_items_cannot_be_deleted(
    conn: sqlite3.Connection, lager: dict[str, int]
) -> None:
    repo.add_item(conn, lager["box"], "Multimeter", qty=1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM container WHERE id = ?", (lager["box"],))


def test_update_and_delete_keep_history(conn: sqlite3.Connection, lager: dict[str, int]) -> None:
    item = repo.add_item(conn, lager["box"], "Multimeter", qty=1)
    repo.update_item(conn, item, name="Multimeter UT61E", tags="messen")
    with pytest.raises(LagerError):
        repo.update_item(conn, item, container_id=1)
    repo.delete_item(conn, item)
    rows = conn.execute("SELECT action, item_name, item_id FROM event ORDER BY id").fetchall()
    assert [r["action"] for r in rows] == ["add", "edit", "delete"]
    assert rows[-1]["item_name"] == "Multimeter UT61E"
    assert all(r["item_id"] is None for r in rows)
