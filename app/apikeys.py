"""API-Schlüssel für Schreibzugriffe (REST, CLI, MCP). Gespeichert wird nur der SHA-256-Hash."""

import hashlib
import secrets
import sqlite3

from app.repo import LagerError, Row


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create(conn: sqlite3.Connection, name: str) -> str:
    """Neuen Schlüssel erzeugen; der Klartext wird nur hier einmal zurückgegeben."""
    if not name.strip():
        raise LagerError("Name für den Schlüssel fehlt")
    key = "kpl_" + secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO api_key (name, key_hash) VALUES (?, ?)", (name.strip(), _hash(key))
        )
    return key


def verify(conn: sqlite3.Connection, key: str) -> bool:
    if not key:
        return False
    row = conn.execute("SELECT id FROM api_key WHERE key_hash = ?", (_hash(key),)).fetchone()
    if row is None:
        return False
    with conn:
        conn.execute("UPDATE api_key SET last_used = datetime('now') WHERE id = ?", (row["id"],))
    return True


def all_keys(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT id, name, created_at, last_used FROM api_key ORDER BY id"
    ).fetchall()


def delete(conn: sqlite3.Connection, key_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM api_key WHERE id = ?", (key_id,))
