"""API-Schlüssel für Schreibzugriffe (REST, CLI, MCP). Gespeichert wird nur der SHA-256-Hash."""

import hashlib
import secrets
import sqlite3

from app.repo import LagerError, Row


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


SCOPES = ("read", "write")


def create(conn: sqlite3.Connection, name: str, scope: str = "write") -> str:
    """Neuen Schlüssel erzeugen (read = nur lesen, write = lesen und schreiben).

    Der Klartext wird nur hier einmal zurückgegeben.
    """
    if not name.strip():
        raise LagerError("Name für den Schlüssel fehlt")
    if scope not in SCOPES:
        raise LagerError("Rechte: read oder write")
    key = "kpl_" + secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO api_key (name, key_hash, scope) VALUES (?, ?, ?)",
            (name.strip(), _hash(key), scope),
        )
    return key


def scope_of(conn: sqlite3.Connection, key: str) -> str | None:
    """Rechte des Schlüssels (und „zuletzt benutzt“ merken); None = unbekannt."""
    if not key:
        return None
    row = conn.execute("SELECT id, scope FROM api_key WHERE key_hash = ?", (_hash(key),)).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute("UPDATE api_key SET last_used = datetime('now') WHERE id = ?", (row["id"],))
    return str(row["scope"])


def verify(conn: sqlite3.Connection, key: str, need: str = "write") -> bool:
    """Schlüssel gültig und für `need` ausreichend? (write schließt read ein)."""
    scope = scope_of(conn, key)
    return scope == "write" or (scope == "read" and need == "read")


def all_keys(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT id, name, scope, created_at, last_used FROM api_key ORDER BY id"
    ).fetchall()


def delete(conn: sqlite3.Connection, key_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM api_key WHERE id = ?", (key_id,))
