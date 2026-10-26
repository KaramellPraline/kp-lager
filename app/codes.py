"""Code-Schema PRÄFIX-Nummer: EUR-001 (Behälter, 3 Stellen), ART-0001 (Gegenstand, 4 Stellen).

Der Code sagt, *was* etwas ist, nie *wo* es steht – der Ort liegt in der Datenbank.
Zähler je Präfix in `meta` (`next:EUR`): gedruckte, unbenutzte Codes werden nie doppelt vergeben.
"""

import re
import sqlite3

ITEM_PREFIX = "ART"
PREFIX_KIND: dict[str, str | None] = {
    "RAU": "raum",
    "REG": "regal",
    "STA": "stapel",
    "EUR": "eurobox",
    "KIS": "kiste",
    "SOR": "sortierkasten",
    "EIN": "einsatz",
    ITEM_PREFIX: None,
}
PREFIX_LABELS = {
    "RAU": "Raum", "REG": "Regal", "STA": "Stellplatz/Kistenberg", "EUR": "Eurobox",
    "KIS": "Kiste/Box", "SOR": "Sortierkasten", "EIN": "Einsatz (Bin)", ITEM_PREFIX: "Gegenstand",
}  # fmt: skip
KIND_PREFIX = {kind: p for p, kind in PREFIX_KIND.items() if kind} | {"sonstiges": "KIS"}
CODE_RE = re.compile(r"^([A-Z]{3})-?0*(\d{1,6})$")


def digits(prefix: str) -> int:
    return 4 if prefix == ITEM_PREFIX else 3


def format_code(prefix: str, number: int) -> str:
    return f"{prefix}-{number:0{digits(prefix)}d}"


def normalize(raw: str) -> str | None:
    """'eur1', 'EUR001', 'Eur-001' -> 'EUR-001'; None, wenn kein gültiger Code des Schemas."""
    m = CODE_RE.match(raw.strip().upper())
    if not m or m.group(1) not in PREFIX_KIND or int(m.group(2)) == 0:
        return None
    return format_code(m.group(1), int(m.group(2)))


def prefix_of(code: str) -> str | None:
    norm = normalize(code)
    return norm[:3] if norm else None


def next_number(conn: sqlite3.Connection, prefix: str) -> int:
    """Erste Nummer nach allen vergebenen und bereits reservierten/gedruckten Codes."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (f"next:{prefix}",)).fetchone()
    reserved = int(row["value"]) if row else 1
    used = conn.execute(
        "SELECT MAX(n) FROM (SELECT CAST(substr(code, 5) AS INTEGER) AS n FROM container"
        " WHERE code LIKE ? UNION ALL SELECT CAST(substr(code, 5) AS INTEGER) FROM item"
        " WHERE code LIKE ?)",
        (f"{prefix}-%", f"{prefix}-%"),
    ).fetchone()[0]
    return max(reserved, (used or 0) + 1)


def mark_used_until(conn: sqlite3.Connection, prefix: str, last_number: int) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE"
            " SET value = MAX(CAST(value AS INTEGER), CAST(excluded.value AS INTEGER))",
            (f"next:{prefix}", str(last_number + 1)),
        )


def reserve(conn: sqlite3.Connection, prefix: str, count: int) -> list[str]:
    """Reserviert `count` neue Codes (z. B. für einen Etiketten-Vorrat)."""
    start = next_number(conn, prefix)
    mark_used_until(conn, prefix, start + count - 1)
    return [format_code(prefix, n) for n in range(start, start + count)]


# --- Einstellungen ---------------------------------------------------------------


def get_setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (f"setting:{key}",)).fetchone()
    return str(row["value"]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"setting:{key}", value),
        )


def auto_item_code(conn: sqlite3.Connection) -> bool:
    """Neue Gegenstände bekommen automatisch einen ART-Code (Standard: an)."""
    return get_setting(conn, "auto_item_code", "1") == "1"


def new_item_code(conn: sqlite3.Connection) -> str | None:
    return reserve(conn, ITEM_PREFIX, 1)[0] if auto_item_code(conn) else None
