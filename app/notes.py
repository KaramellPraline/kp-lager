"""Sprachaufnahmen (Diktate): Audio sichern, Transkript speichern, Haiku-Prompt mit Zeitstempel."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from app import prompt
from app.repo import LagerError, Row

MAX_BYTES = 60 * 1024 * 1024  # ca. 1 h Opus-Audio


def save_audio(data: bytes, folder: Path, content_type: str) -> str:
    if not data:
        raise LagerError("Aufnahme ist leer")
    if len(data) > MAX_BYTES:
        raise LagerError("Aufnahme zu groß (max. 60 MB)")
    ext = ".m4a" if "mp4" in content_type or "aac" in content_type else ".webm"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (folder / name).write_bytes(data)
    return name


def create(conn: sqlite3.Connection, audio: str, duration: int) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO voice_note (audio, duration) VALUES (?, ?)", (audio, max(0, duration))
        )
    assert cur.lastrowid is not None
    return cur.lastrowid


def get(conn: sqlite3.Connection, note_id: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM voice_note WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        raise LagerError("Aufnahme nicht gefunden")
    return row


def all_notes(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute("SELECT * FROM voice_note ORDER BY id DESC").fetchall()


def set_result(conn: sqlite3.Connection, note_id: int, text: str = "", error: str = "") -> None:
    with conn:
        conn.execute(
            "UPDATE voice_note SET transcript = ?, status = ?, error = ? WHERE id = ?",
            (text.strip(), "fehler" if error else "fertig", error, note_id),
        )


def delete(conn: sqlite3.Connection, note_id: int, folder: Path) -> None:
    note = get(conn, note_id)
    if note["audio"]:
        (folder / note["audio"]).unlink(missing_ok=True)
    with conn:
        conn.execute("DELETE FROM voice_note WHERE id = ?", (note_id,))


def stamp(note: Row) -> str:
    """'26.10.2026 21:14' aus created_at (lokale Zeit)."""
    return datetime.fromisoformat(note["created_at"]).strftime("%d.%m.%Y %H:%M")


def duration_label(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def chat_prompt(note: Row, ctx: "prompt.Context | None" = None) -> str:
    return prompt.for_dictation(
        note["transcript"], stamp(note), duration_label(note["duration"]), ctx
    )


def filename(note: Row) -> str:
    ts = datetime.fromisoformat(note["created_at"]).strftime("%Y-%m-%d_%H%M")
    return f"haiku-diktat_{ts}.txt"
