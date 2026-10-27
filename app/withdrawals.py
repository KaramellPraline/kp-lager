"""Entnahmen: Menge sofort abbuchen, nach 7 Tagen automatisch bestätigt, bis dahin stornierbar.

Gezählte Teile: Menge sinkt sofort, Storno bucht zurück.
Ungezählte Teile: gelten als „entnommen“; nach der Frist werden sie archiviert (nicht gelöscht).
"""

import sqlite3
import time

from app import repo
from app.repo import LagerError, Row

DAYS = 7
_last_check = 0.0


def take(conn: sqlite3.Connection, item_id: int, qty: int = 1, note: str = "") -> int:
    item = repo.get_item(conn, item_id)
    if item["archived"]:
        raise LagerError(f"„{item['name']}“ ist bereits archiviert")
    amount: int | None = None
    if item["qty"] is not None:
        if qty < 1:
            raise LagerError("Menge mindestens 1")
        if qty > item["qty"]:
            raise LagerError(f"Nur {item['qty']} vorhanden")
        repo.change_qty(conn, item_id, -qty, note=note or "Entnahme")
        amount = qty
    else:
        with conn:
            conn.execute(
                "INSERT INTO event (item_id, item_name, container_id, action, note)"
                " VALUES (?, ?, ?, 'take', ?)",
                (item_id, item["name"], item["container_id"], note or "Entnahme"),
            )
    with conn:
        cur = conn.execute(
            "INSERT INTO withdrawal (item_id, item_name, container_id, qty, confirm_at)"
            " VALUES (?, ?, ?, ?, datetime('now', ?))",
            (item_id, item["name"], item["container_id"], amount, f"+{DAYS} days"),
        )
    assert cur.lastrowid is not None
    return cur.lastrowid


def get(conn: sqlite3.Connection, wid: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM withdrawal WHERE id = ?", (wid,)).fetchone()
    if row is None:
        raise LagerError("Entnahme nicht gefunden")
    return row


def cancel(conn: sqlite3.Connection, wid: int) -> str:
    w = get(conn, wid)
    if w["state"] != "offen":
        raise LagerError("Entnahme ist nicht mehr offen")
    if w["item_id"] is not None and w["qty"]:
        repo.change_qty(conn, w["item_id"], w["qty"], note="Entnahme storniert")
    with conn:
        conn.execute("UPDATE withdrawal SET state = 'storniert' WHERE id = ?", (wid,))
    return f"Entnahme von „{w['item_name']}“ storniert"


def confirm_due(conn: sqlite3.Connection, force: bool = False) -> int:
    """Fällige Entnahmen bestätigen (höchstens einmal pro Minute, außer force)."""
    global _last_check
    if not force and time.monotonic() - _last_check < 60:
        return 0
    _last_check = time.monotonic()
    due = conn.execute(
        "SELECT * FROM withdrawal WHERE state = 'offen' AND confirm_at <= datetime('now')"
    ).fetchall()
    with conn:
        for w in due:
            conn.execute("UPDATE withdrawal SET state = 'bestaetigt' WHERE id = ?", (w["id"],))
            if w["item_id"] is not None and w["qty"] is None:  # ungezählt -> archivieren
                conn.execute("UPDATE item SET archived = 1 WHERE id = ?", (w["item_id"],))
    return len(due)


def open_for_item(conn: sqlite3.Connection, item_id: int) -> list[Row]:
    return conn.execute(
        "SELECT *, CAST(julianday(confirm_at) - julianday('now') + 0.999 AS INTEGER) AS days_left"
        " FROM withdrawal WHERE item_id = ? AND state = 'offen' ORDER BY id DESC",
        (item_id,),
    ).fetchall()


def recent(conn: sqlite3.Connection, limit: int = 100) -> list[Row]:
    return conn.execute(
        "SELECT *, CAST(julianday(confirm_at) - julianday('now') + 0.999 AS INTEGER) AS days_left"
        " FROM withdrawal ORDER BY state != 'offen', id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def open_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM withdrawal WHERE state = 'offen'").fetchone()[0])
