"""Notiz- und Pinout-Karten an Teilen und Behältern (z. B. Pinbelegung, Einstellungen, Maße)."""

import re
import sqlite3
from typing import Any

from app.repo import LagerError, Row

KINDS = {"note": "Notiz", "pinout": "Pinout"}


def add(
    conn: sqlite3.Connection,
    title: str,
    body: str,
    kind: str = "note",
    item_id: int | None = None,
    container_id: int | None = None,
) -> int:
    if kind not in KINDS:
        raise LagerError("Unbekannte Kartenart")
    if (item_id is None) == (container_id is None):
        raise LagerError("Karte gehört entweder zu einem Teil oder zu einem Behälter")
    if not title.strip():
        raise LagerError("Titel fehlt")
    with conn:
        cur = conn.execute(
            "INSERT INTO card (item_id, container_id, kind, title, body) VALUES (?, ?, ?, ?, ?)",
            (item_id, container_id, kind, title.strip(), body.strip()),
        )
    assert cur.lastrowid is not None
    return cur.lastrowid


def get(conn: sqlite3.Connection, card_id: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM card WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise LagerError("Karte nicht gefunden")
    return row


def update(conn: sqlite3.Connection, card_id: int, title: str, body: str) -> None:
    if not title.strip():
        raise LagerError("Titel fehlt")
    get(conn, card_id)
    with conn:
        conn.execute(
            "UPDATE card SET title = ?, body = ? WHERE id = ?",
            (title.strip(), body.strip(), card_id),
        )


def delete(conn: sqlite3.Connection, card_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM card WHERE id = ?", (card_id,))


def pinout_rows(body: str) -> list[list[str]]:
    """Zeilen „Pin; Funktion; Hinweis“ (oder mit Tab, |, Leerzeichen) -> Tabellenzeilen."""
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = (
            re.split(r"\s*[;|\t]\s*", line) if re.search(r"[;|\t]", line) else line.split(None, 2)
        )
        rows.append([p.strip() for p in parts])
    return rows


def _with_rows(rows: list[Row]) -> list[dict[str, Any]]:
    return [
        {**dict(r), "rows": pinout_rows(r["body"]) if r["kind"] == "pinout" else []} for r in rows
    ]


def for_item(conn: sqlite3.Connection, item_id: int) -> list[dict[str, Any]]:
    return _with_rows(
        conn.execute("SELECT * FROM card WHERE item_id = ? ORDER BY id", (item_id,)).fetchall()
    )


def for_container(conn: sqlite3.Connection, container_id: int) -> list[dict[str, Any]]:
    return _with_rows(
        conn.execute(
            "SELECT * FROM card WHERE container_id = ? ORDER BY id", (container_id,)
        ).fetchall()
    )
