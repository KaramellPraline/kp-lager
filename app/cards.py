"""Notiz- und Pinout-Karten an Teilen und Behältern (z. B. Pinbelegung, Einstellungen, Maße)."""

import re
import sqlite3
from typing import Any

from app.repo import LagerError, Row

# Kartenarten: Schlüssel -> (Name, Hinweis fürs Eingabefeld, Titelvorschlag)
KIND_INFO = {
    "note": ("Notiz", "Freier Text", "Notiz"),
    "pinout": ("Pinout", "Eine Zeile je Pin: 1; VCC; 3,3 V", "Pinbelegung"),
    "spec": ("Eigenschaften", "Eine Zeile je Wert: Spannung; 3,3 V", "Technische Daten"),
    "checklist": ("Checkliste", "Eine Zeile je Punkt; [x] am Anfang = erledigt", "Checkliste"),
    "link": ("Links", "Eine Zeile je Link: https://… oder Titel; https://…", "Links"),
}
KINDS = {k: v[0] for k, v in KIND_INFO.items()}


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


def checklist_rows(body: str) -> list[list[str]]:
    """Zeilen „[x] Text“ / „[ ] Text“ / „Text“ -> [„1“|„0“, Text]."""
    rows = []
    for line in body.splitlines():
        m = re.match(r"\s*(?:[-*]\s*)?(\[[xX ]?\])?\s*(.+)", line)
        if m and m.group(2).strip():
            rows.append(
                ["1" if m.group(1) and m.group(1)[1:2] in "xX" else "0", m.group(2).strip()]
            )
    return rows


def link_rows(body: str) -> list[list[str]]:
    """Zeilen „Titel; URL“ oder nur „URL“ -> [Titel, URL]; nur http(s)-Links."""
    rows = []
    for line in body.splitlines():
        parts = [p.strip() for p in line.split(";", 1)]
        url = parts[-1]
        if re.match(r"https?://\S+$", url):
            rows.append([parts[0] if len(parts) > 1 else url, url])
    return rows


def _rows_of(kind: str, body: str) -> list[list[str]]:
    if kind in ("pinout", "spec"):
        return pinout_rows(body)
    if kind == "checklist":
        return checklist_rows(body)
    if kind == "link":
        return link_rows(body)
    return []


def _with_rows(rows: list[Row]) -> list[dict[str, Any]]:
    return [{**dict(r), "rows": _rows_of(r["kind"], r["body"])} for r in rows]


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
