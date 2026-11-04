"""Presets (Klassen) je Teile-Typ: gespeicherte Feldwerte als Schnellwahl beim Anlegen.

Gedacht für Verbrauchsmaterial (Filament, Harz): „PLA“, „PA12-CF“ … füllen Kunststoff, Zusatz,
Spulentyp, Leergewicht usw. mit einem Klick vor. Ein manuell eingetragener Hersteller wird
über `catalog.remember_brand` in Auswahl und Preset-Ersteller übernommen.
"""

import json
import sqlite3
from typing import Any

from app.repo import LagerError


def all_for(conn: sqlite3.Connection, kind: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM preset WHERE kind = ? ORDER BY name COLLATE NOCASE", (kind,))
    out = []
    for r in rows:
        try:
            data = json.loads(r["data"] or "{}")
        except ValueError:
            data = {}
        out.append({"id": r["id"], "name": r["name"], "data": data})
    return out


def save(conn: sqlite3.Connection, kind: str, name: str, values: dict[str, str]) -> None:
    name = name.strip()
    if not name:
        raise LagerError("Bitte dem Preset einen Namen geben")
    data = {k: v.strip() for k, v in values.items() if v and v.strip()}
    if not data:
        raise LagerError("Zum Speichern erst Felder ausfüllen")
    with conn:
        conn.execute(
            "INSERT INTO preset (kind, name, data) VALUES (?, ?, ?)"
            " ON CONFLICT(kind, name) DO UPDATE SET data = excluded.data",
            (kind, name, json.dumps(data, ensure_ascii=False)),
        )


def delete(conn: sqlite3.Connection, preset_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM preset WHERE id = ?", (preset_id,))
