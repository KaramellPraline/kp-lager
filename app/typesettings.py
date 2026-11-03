"""Einstellungen je Typ (Katalog, eigene Typen, Material-Profile `mat:fil` …):
Standard-Mindestbestand, Haltbarkeit nach dem Öffnen, Etikettenvorlagen."""

import sqlite3
from typing import Any

from app.repo import LagerError

# Typ-Schlüssel eines Teils (für die Verknüpfung in SQL): ctype, sonst Material-Profil
TYPE_KEY_SQL = "COALESCE(i.ctype, 'mat:' || i.material)"


def key_of(item: Any) -> str:
    if item["ctype"]:
        return str(item["ctype"])
    return f"mat:{item['material']}" if item["material"] else ""


def get(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM type_setting WHERE key = ?", (key,)).fetchone()
    if row is None:
        return {
            "key": key,
            "min_qty": None,
            "shelf_months": None,
            "label_main": "",
            "label_extra": "",
        }
    return dict(row)


def save(
    conn: sqlite3.Connection,
    key: str,
    min_qty: int | None,
    shelf_months: int | None,
    label_main: str = "",
    label_extra: str = "",
) -> None:
    if not key:
        raise LagerError("Typ fehlt")
    for n in (min_qty, shelf_months):
        if n is not None and n < 0:
            raise LagerError("Bitte keine negativen Zahlen")
    with conn:
        conn.execute(
            "INSERT INTO type_setting (key, min_qty, shelf_months, label_main, label_extra)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET min_qty = excluded.min_qty,"
            " shelf_months = excluded.shelf_months, label_main = excluded.label_main,"
            " label_extra = excluded.label_extra",
            (key, min_qty, shelf_months, label_main.strip(), label_extra.strip()),
        )


def effective_min(conn: sqlite3.Connection, item: Any) -> tuple[int | None, bool]:
    """(Mindestbestand, kommt vom Typ?) – der Wert am Teil hat Vorrang."""
    if item["min_qty"] is not None:
        return int(item["min_qty"]), False
    key = key_of(item)
    default = get(conn, key)["min_qty"] if key else None
    return (int(default), True) if default is not None else (None, False)
