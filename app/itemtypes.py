"""Typen/Kategorien von Teilen (mechanical, electronic, …), Codes TYP-001, unterwegs erweiterbar."""

import sqlite3

from app import codes
from app.repo import LagerError, Row


def all_types(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT t.*, (SELECT COUNT(*) FROM item i WHERE i.type_id = t.id AND i.archived = 0) AS n"
        " FROM item_type t ORDER BY t.name COLLATE NOCASE"
    ).fetchall()


def get(conn: sqlite3.Connection, type_id: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM item_type WHERE id = ?", (type_id,)).fetchone()
    if row is None:
        raise LagerError("Typ nicht gefunden")
    return row


def by_code(conn: sqlite3.Connection, code: str) -> Row | None:
    row: Row | None = conn.execute("SELECT * FROM item_type WHERE code = ?", (code,)).fetchone()
    return row


def by_name(conn: sqlite3.Connection, name: str) -> Row | None:
    row: Row | None = conn.execute(
        "SELECT * FROM item_type WHERE name = ? COLLATE NOCASE", (name.strip(),)
    ).fetchone()
    return row


def create(conn: sqlite3.Connection, name: str) -> int:
    """Neuen Typ anlegen (bekommt den nächsten TYP-Code); vorhandener Name -> dessen ID."""
    name = " ".join(name.split()).lower()  # Typen immer kleingeschrieben
    if not name:
        raise LagerError("Typname fehlt")
    if (existing := by_name(conn, name)) is not None:
        return int(existing["id"])
    code = codes.reserve(conn, codes.TYPE_PREFIX, 1)[0]
    with conn:
        cur = conn.execute("INSERT INTO item_type (code, name) VALUES (?, ?)", (code, name))
    assert cur.lastrowid is not None
    return cur.lastrowid


def resolve(conn: sqlite3.Connection, type_id: str, new_name: str = "") -> int | None:
    """Formularwert -> Typ-ID: leer = kein Typ, 'neu' + Name = anlegen, sonst vorhandene ID."""
    if type_id == "neu" or (not type_id and new_name.strip()):
        return create(conn, new_name)
    if not type_id:
        return None
    if not type_id.isdigit():
        raise LagerError("Ungültiger Typ")
    return int(get(conn, int(type_id))["id"])


def rename(conn: sqlite3.Connection, type_id: int, name: str) -> None:
    name = " ".join(name.split()).lower()  # Typen immer kleingeschrieben
    if not name:
        raise LagerError("Typname fehlt")
    other = by_name(conn, name)
    if other is not None and other["id"] != type_id:
        raise LagerError(f"Typ „{name}“ gibt es schon")
    with conn:
        conn.execute("UPDATE item_type SET name = ? WHERE id = ?", (name, type_id))


def delete(conn: sqlite3.Connection, type_id: int) -> None:
    t = get(conn, type_id)
    if conn.execute("SELECT 1 FROM item WHERE type_id = ?", (type_id,)).fetchone():
        raise LagerError(f"Typ „{t['name']}“ wird noch verwendet")
    with conn:
        conn.execute("DELETE FROM item_type WHERE id = ?", (type_id,))


def items_of(conn: sqlite3.Connection, type_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM item WHERE type_id = ? AND archived = 0 ORDER BY name", (type_id,)
    ).fetchall()


def names(conn: sqlite3.Connection) -> list[str]:
    """Für Prompts: aktuelle Typnamen (inkl. unterwegs angelegter)."""
    return [r["name"] for r in all_types(conn)]
