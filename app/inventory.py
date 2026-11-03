"""Inventur: Behälter Stück für Stück abhaken, Mengen korrigieren, „zuletzt geprüft“ merken.

Eine Runde endet mit `finish`; Teile, die danach bestätigt wurden, zählen für die nächste Runde.
"""

import sqlite3
from typing import Any

from app import repo
from app.repo import LagerError

DUE_DAYS = 180


def due(conn: sqlite3.Connection, days: int = DUE_DAYS) -> list[dict[str, Any]]:
    """Behälter mit Teilen, deren Inventur fehlt oder länger als `days` Tage her ist."""
    rows = conn.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM item i WHERE i.container_id = c.id"
        " AND i.archived = 0) AS n FROM container c"
        " WHERE EXISTS (SELECT 1 FROM item i WHERE i.container_id = c.id AND i.archived = 0)"
        " AND (c.checked_at IS NULL OR c.checked_at < datetime('now', 'localtime', ?))"
        " ORDER BY c.checked_at IS NOT NULL, c.checked_at, c.name",
        (f"-{int(days)} days",),
    ).fetchall()
    return [{**dict(r), "path": repo.path_label(conn, r["id"])} for r in rows]


def items(conn: sqlite3.Connection, container_id: int) -> list[dict[str, Any]]:
    """Teile des Behälters; `checked` = in der laufenden Runde schon bestätigt."""
    node = repo.get_container(conn, container_id)
    if node is None:
        raise LagerError("Behälter nicht gefunden")
    last = node["checked_at"]
    rows = conn.execute(
        "SELECT * FROM item WHERE container_id = ? AND archived = 0 ORDER BY name COLLATE NOCASE",
        (container_id,),
    ).fetchall()
    return [
        {**dict(r), "checked": bool(r["checked_at"]) and (not last or r["checked_at"] > last)}
        for r in rows
    ]


def confirm_item(conn: sqlite3.Connection, item_id: int, qty: int | None = None) -> str:
    """Teil bestätigen; weicht die gezählte Menge ab, wird sie gebucht (Notiz „Inventur“)."""
    item = repo.get_item(conn, item_id)
    msg = f"„{item['name']}“ bestätigt"
    if qty is not None and item["qty"] is not None and qty != item["qty"]:
        if qty < 0:
            raise LagerError("Menge darf nicht negativ sein")
        repo.change_qty(conn, item_id, qty - item["qty"], note="Inventur")
        msg += f" · Menge {item['qty']} → {qty}"
    with conn:
        conn.execute(
            "UPDATE item SET checked_at = datetime('now', 'localtime') WHERE id = ?", (item_id,)
        )
    return msg


def confirm_by_code(conn: sqlite3.Connection, container_id: int, code: str) -> str:
    item = repo.get_item_by_code(conn, code)
    if item is None or item["container_id"] != container_id:
        raise LagerError(f"{code} gehört nicht in diesen Behälter")
    return confirm_item(conn, item["id"])


def finish(conn: sqlite3.Connection, container_id: int) -> int:
    """Runde abschließen; gibt die Zahl der Teile zurück, die nicht einzeln bestätigt wurden."""
    todo = [i for i in items(conn, container_id) if not i["checked"]]
    with conn:
        conn.execute(
            "UPDATE container SET checked_at = datetime('now', 'localtime') WHERE id = ?",
            (container_id,),
        )
    return len(todo)
