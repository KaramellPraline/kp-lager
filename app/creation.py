"""Teile mit Kategorie anlegen (API, MCP, CLI): Code, Eigenschaften, Einzelstücke, Etikett.

Gleiche Regeln wie auf der Startseite: Kabel/Netzteile sind Einzelstücke (je Stück ein Eintrag
mit eigenem Etikett), die Kategorie bestimmt Code-Präfix und Eigenschafts-Profil.
"""

import sqlite3
from typing import Any

from app import codes, materials, repo
from app.repo import LagerError

MAX_COUNT = 50


def add(
    conn: sqlite3.Connection,
    container_id: int,
    name: str,
    cat: str = codes.ITEM_PREFIX,
    qty: int | None = None,
    unit: str = "",
    specs: dict[str, str] | None = None,
    count: int = 1,
    review: bool = False,
) -> list[int]:
    """Legt `count` Teile an; gibt die IDs zurück."""
    cat = (cat or codes.ITEM_PREFIX).strip().upper()
    if cat not in codes.ITEM_PREFIXES:
        raise LagerError(f"Unbekannte Kategorie {cat}. Gültig: {', '.join(codes.ITEM_PREFIXES)}")
    name = name.strip()
    individual = cat in repo.INDIVIDUAL
    given = {k: str(v) for k, v in (specs or {}).items() if str(v).strip()}
    profile = materials.PREFIX_MATERIAL.get(cat)
    if not name and not given:
        raise LagerError("Name fehlt")
    copies = max(1, min(count, MAX_COUNT)) if individual else 1
    ids: list[int] = []
    for _ in range(copies):
        code = (
            codes.new_item_code(conn)
            if cat == codes.ITEM_PREFIX
            else codes.reserve(conn, cat, 1)[0]
        )
        item_id = repo.add_item(
            conn, container_id, name or "Neu", qty=None if individual else qty,
            unit="" if individual else unit, code=code,
        )  # fmt: skip
        if profile:
            if profile in ("cbl", "psu"):  # Felder aus den Angaben, Rest aus dem Namen erkannt
                form = materials.auto_specs(profile, name, given)
            else:
                keys = {f.key for f in materials.FIELDS[profile]}
                form = {
                    f"spec_{k}": ok for k, v in given.items()
                    if k in keys and (ok := materials.plausible(k, v))
                }  # fmt: skip
            materials.save_specs(conn, item_id, profile, form)
        if review:
            repo.update_item(conn, item_id, review=1)
        ids.append(item_id)
    return ids


def summary(conn: sqlite3.Connection, item_ids: list[int]) -> list[dict[str, Any]]:
    return [dict(repo.get_item(conn, i)) for i in item_ids]
