"""Code-Schema PRÄFIX-Nummer: EUR-001 (Behälter, 3 Stellen), ART-0001 (Gegenstand, 4 Stellen).

Der Code sagt, *was* etwas ist, nie *wo* es steht – der Ort liegt in der Datenbank.
Zähler je Präfix in `meta` (`next:EUR`): gedruckte, unbenutzte Codes werden nie doppelt vergeben.
"""

import re
import sqlite3

ITEM_PREFIX = "ART"
TYPE_PREFIX = "TYP"  # Typen/Kategorien von Teilen (item_type)
# Präfix -> Art (None = Teil/Typ), Präfix -> Name, Art -> Präfix; gefüllt von app.kinds
PREFIX_KIND: dict[str, str | None] = {}
PREFIX_LABELS: dict[str, str] = {}
KIND_PREFIX: dict[str, str] = {}
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


def highest_used(conn: sqlite3.Connection, prefix: str) -> int:
    """Höchste Nummer, die einem Behälter oder Gegenstand zugeordnet ist (0 = keine)."""
    used = conn.execute(
        "SELECT MAX(n) FROM (SELECT CAST(substr(code, 5) AS INTEGER) AS n FROM container"
        " WHERE code LIKE ? UNION ALL SELECT CAST(substr(code, 5) AS INTEGER) FROM item"
        " WHERE code LIKE ? UNION ALL SELECT CAST(substr(code, 5) AS INTEGER) FROM item_type"
        " WHERE code LIKE ?)",
        (f"{prefix}-%", f"{prefix}-%", f"{prefix}-%"),
    ).fetchone()[0]
    return int(used or 0)


def next_number(conn: sqlite3.Connection, prefix: str) -> int:
    """Erste Nummer nach allen vergebenen und bereits reservierten/gedruckten Codes."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (f"next:{prefix}",)).fetchone()
    reserved = int(row["value"]) if row else 1
    return max(reserved, highest_used(conn, prefix) + 1)


def set_next(conn: sqlite3.Connection, prefix: str, number: int) -> None:
    """Admin: nächste Nummer festlegen (auch zurück), aber nie auf eine vergebene."""
    if prefix not in PREFIX_KIND:
        raise ValueError(f"Unbekanntes Präfix {prefix}")
    lowest = highest_used(conn, prefix) + 1
    if number < lowest:
        raise ValueError(
            f"{format_code(prefix, number)} oder höher ist schon vergeben – mindestens {lowest}"
        )
    if number > 999_999:
        raise ValueError("Nummer zu groß (max. 999999)")
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"next:{prefix}", str(number)),
        )


def reset_counter(conn: sqlite3.Connection, prefix: str) -> int:
    """Admin: reservierte, unbenutzte Nummern freigeben -> nächste = höchste vergebene + 1."""
    with conn:
        conn.execute("DELETE FROM meta WHERE key = ?", (f"next:{prefix}",))
    return next_number(conn, prefix)


def used_codes(conn: sqlite3.Connection, prefix: str) -> list[dict[str, object]]:
    """Alle vergebenen Codes eines Präfixes mit Objekt (Behälter oder Gegenstand)."""
    rows = conn.execute(
        "SELECT code, 'node' AS type, id, name FROM container WHERE code LIKE ?"
        " UNION ALL SELECT code, 'item', id, name FROM item WHERE code LIKE ?"
        " UNION ALL SELECT code, 'type', id, name FROM item_type WHERE code LIKE ? ORDER BY code",
        (f"{prefix}-%", f"{prefix}-%", f"{prefix}-%"),
    ).fetchall()
    return [dict(r) for r in rows]


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


import app.kinds  # noqa: E402, F401  (füllt die Präfix-Tabellen)
