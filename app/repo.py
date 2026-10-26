"""Datenzugriff: Behälter-Baum, Items und Protokoll. Alle Funktionen committen selbst."""

import sqlite3
from string import ascii_uppercase

Row = sqlite3.Row

KINDS = (
    "raum", "regal", "ebene", "stapel", "eurobox", "kiste", "sortierkasten", "fach", "sonstiges",
)  # fmt: skip


class LagerError(ValueError):
    """Fachlicher Fehler (z. B. Bestand < 0, Behälter in sich selbst verschieben)."""


# --- Behälter -----------------------------------------------------------------


def parse_grid(grid: str) -> list[str]:
    """'4x3' (Spalten x Zeilen) -> ['A1', 'A2', 'A3', 'A4', 'B1', …, 'C4']."""
    try:
        cols, rows = (int(p) for p in grid.lower().split("x"))
    except ValueError:
        raise LagerError(f"Raster '{grid}' ungültig, erwartet z. B. '6x8'") from None
    if not (1 <= cols <= 30 and 1 <= rows <= len(ascii_uppercase)):
        raise LagerError(f"Raster '{grid}' außerhalb 1-30 Spalten / 1-26 Zeilen")
    return [f"{ascii_uppercase[r]}{c + 1}" for r in range(rows) for c in range(cols)]


def create_container(
    conn: sqlite3.Connection,
    name: str,
    kind: str,
    parent_id: int | None = None,
    code: str | None = None,
    position: str | None = None,
    grid: str | None = None,
    notes: str = "",
) -> int:
    """Legt einen Behälter an. Mit `grid` werden die Fächer als Kind-Behälter erzeugt."""
    if kind not in KINDS:
        raise LagerError(f"Unbekannte Art '{kind}'")
    slots = parse_grid(grid) if grid else []
    with conn:
        cur = conn.execute(
            "INSERT INTO container (code, parent_id, kind, name, position, grid, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, parent_id, kind, name, position, grid, notes),
        )
        cid = cur.lastrowid
        assert cid is not None
        conn.executemany(
            "INSERT INTO container (parent_id, kind, name, position) VALUES (?, 'fach', ?, ?)",
            [(cid, f"Fach {s}", s) for s in slots],
        )
    return cid


def get_container(conn: sqlite3.Connection, container_id: int) -> Row | None:
    row: Row | None = conn.execute(
        "SELECT * FROM container WHERE id = ?", (container_id,)
    ).fetchone()
    return row


def get_container_by_code(conn: sqlite3.Connection, code: str) -> Row | None:
    row: Row | None = conn.execute("SELECT * FROM container WHERE code = ?", (code,)).fetchone()
    return row


def children(conn: sqlite3.Connection, container_id: int | None) -> list[Row]:
    """Direkte Unterbehälter; `None` = oberste Ebene (Räume)."""
    return conn.execute(
        "SELECT * FROM container WHERE parent_id IS ? ORDER BY position, name", (container_id,)
    ).fetchall()


def container_path(conn: sqlite3.Connection, container_id: int) -> list[Row]:
    """Pfad von der Wurzel bis zum Behälter selbst, z. B. Keller › Regal 1 › Box 0042 › Fach B3."""
    rows = conn.execute(
        """
        WITH RECURSIVE up(id, parent_id, depth) AS (
            SELECT id, parent_id, 0 FROM container WHERE id = ?
            UNION ALL
            SELECT c.id, c.parent_id, up.depth + 1 FROM container c JOIN up ON c.id = up.parent_id
        )
        SELECT c.* FROM up JOIN container c ON c.id = up.id ORDER BY up.depth DESC
        """,
        (container_id,),
    ).fetchall()
    return rows


def path_label(conn: sqlite3.Connection, container_id: int) -> str:
    return " › ".join(r["name"] for r in container_path(conn, container_id))


def move_container(conn: sqlite3.Connection, container_id: int, new_parent_id: int | None) -> None:
    """Behälter umziehen (z. B. Kiste aus dem Stapel ins Regal). Verhindert Zyklen."""
    if new_parent_id is not None and any(
        r["id"] == container_id for r in container_path(conn, new_parent_id)
    ):
        raise LagerError("Behälter kann nicht in sich selbst oder einen Unterbehälter")
    with conn:
        conn.execute(
            "UPDATE container SET parent_id = ?, position = NULL, updated_at = datetime('now')"
            " WHERE id = ?",
            (new_parent_id, container_id),
        )
        conn.execute(
            "INSERT INTO event (container_id, action, note) VALUES (?, 'move', ?)",
            (container_id, f"nach {new_parent_id}"),
        )


def assign_code(conn: sqlite3.Connection, container_id: int, code: str) -> None:
    """Etikett nachträglich zuordnen (z. B. Sortierkasten bekommt QR)."""
    with conn:
        conn.execute(
            "UPDATE container SET code = ?, updated_at = datetime('now') WHERE id = ?",
            (code, container_id),
        )


# --- Items ----------------------------------------------------------------------


def _log(
    conn: sqlite3.Connection, item: Row, action: str, delta: int | None = None, note: str = ""
) -> None:
    conn.execute(
        "INSERT INTO event (item_id, item_name, container_id, action, delta, note)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (item["id"], item["name"], item["container_id"], action, delta, note),
    )


def get_item(conn: sqlite3.Connection, item_id: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise LagerError(f"Item {item_id} existiert nicht")
    return row


def add_item(
    conn: sqlite3.Connection,
    container_id: int,
    name: str,
    qty: int | None = None,
    qty_hint: str = "",
    unit: str = "",
    tags: str = "",
    notes: str = "",
    action: str = "add",
) -> int:
    if qty is not None and qty < 0:
        raise LagerError("Menge darf nicht negativ sein")
    with conn:
        cur = conn.execute(
            "INSERT INTO item (container_id, name, qty, qty_hint, unit, tags, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (container_id, name.strip(), qty, qty_hint, unit, tags, notes),
        )
        item_id = cur.lastrowid
        assert item_id is not None
        _log(conn, get_item(conn, item_id), action, qty)
    return item_id


def items_in(conn: sqlite3.Connection, container_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM item WHERE container_id = ? ORDER BY name", (container_id,)
    ).fetchall()


def change_qty(conn: sqlite3.Connection, item_id: int, delta: int, note: str = "") -> int | None:
    """Entnehmen (delta < 0) / Einlagern (delta > 0). Ungezählte Items: nur Protokoll."""
    item = get_item(conn, item_id)
    new_qty = item["qty"]
    if new_qty is not None:
        new_qty += delta
        if new_qty < 0:
            raise LagerError(f"Nur {item['qty']} vorhanden")
    with conn:
        conn.execute(
            "UPDATE item SET qty = ?, updated_at = datetime('now') WHERE id = ?",
            (new_qty, item_id),
        )
        _log(conn, item, "take" if delta < 0 else "put", delta, note)
    return new_qty  # type: ignore[no-any-return]


def move_item(conn: sqlite3.Connection, item_id: int, container_id: int) -> None:
    item = get_item(conn, item_id)
    with conn:
        conn.execute(
            "UPDATE item SET container_id = ?, updated_at = datetime('now') WHERE id = ?",
            (container_id, item_id),
        )
        _log(conn, item, "move", note=f"von {item['container_id']} nach {container_id}")


def update_item(conn: sqlite3.Connection, item_id: int, **fields: str | int | None) -> None:
    allowed = {"name", "qty", "qty_hint", "unit", "tags", "notes", "photo"}
    if not fields or not set(fields) <= allowed:
        raise LagerError(f"Erlaubte Felder: {sorted(allowed)}")
    item = get_item(conn, item_id)
    sets = ", ".join(f"{k} = ?" for k in fields)
    with conn:
        conn.execute(
            f"UPDATE item SET {sets}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), item_id),
        )
        _log(conn, item, "edit", note=", ".join(fields))


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    item = get_item(conn, item_id)
    with conn:
        _log(conn, item, "delete")
        conn.execute("DELETE FROM item WHERE id = ?", (item_id,))


def history(conn: sqlite3.Connection, item_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM event WHERE item_id = ? ORDER BY id DESC", (item_id,)
    ).fetchall()
