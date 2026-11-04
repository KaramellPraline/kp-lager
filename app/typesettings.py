"""Einstellungen je Typ (Katalog, eigene Typen, Material-Profile `mat:fil` …):
Standard-Mindestbestand, Haltbarkeit nach dem Öffnen, Etikettenvorlagen."""

import json
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
            "required": "",
            "defaults": "",
        }
    return dict(row)


def required_keys(conn: sqlite3.Connection, key: str) -> set[str]:
    """Felder, die beim Anlegen dieses Typs ausgefüllt sein müssen."""
    return {k for k in str(get(conn, key).get("required") or "").split(",") if k}


def save_required(conn: sqlite3.Connection, key: str, fields: list[str]) -> None:
    if not key:
        raise LagerError("Typ fehlt")
    with conn:
        conn.execute(
            "INSERT INTO type_setting (key, required) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET required = excluded.required",
            (key, ",".join(dict.fromkeys(fields))),
        )


def kept_values(conn: sqlite3.Connection, key: str) -> dict[str, str]:
    """Gemerkte Standardwerte (Felder mit „merken“), die beim nächsten Anlegen vorbelegt sind."""
    try:
        data = json.loads(str(get(conn, key).get("defaults") or "{}"))
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_kept(conn: sqlite3.Connection, key: str, values: dict[str, str]) -> None:
    if not key:
        raise LagerError("Typ fehlt")
    raw = json.dumps({k: v for k, v in values.items() if v}, ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO type_setting (key, defaults) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET defaults = excluded.defaults",
            (key, raw),
        )


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


def save_layout(conn: sqlite3.Connection, key: str, layout: dict[str, Any] | None) -> None:
    """Etiketten-Layout des Typs speichern (None = Standard wiederherstellen)."""
    from app import labels

    if not key:
        raise LagerError("Typ fehlt")
    raw = json.dumps(labels.parse_layout(layout), ensure_ascii=False) if layout else ""
    with conn:
        conn.execute(
            "INSERT INTO type_setting (key, label_layout) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET label_layout = excluded.label_layout",
            (key, raw),
        )


def effective_min(conn: sqlite3.Connection, item: Any) -> tuple[int | None, bool]:
    """(Mindestbestand, kommt vom Typ?) – der Wert am Teil hat Vorrang."""
    if item["min_qty"] is not None:
        return int(item["min_qty"]), False
    key = key_of(item)
    default = get(conn, key)["min_qty"] if key else None
    return (int(default), True) if default is not None else (None, False)
