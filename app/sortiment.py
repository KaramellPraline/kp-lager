"""Sortiment nach Typ: Katalog-Typen, eigene Typen und Material-Profile (Filament, Harz,
Elektronik, Kabel, Netzteil) einheitlich – Filter je Feld, natürliche Sortierung, Variantenraster.
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from app import catalog, materials, repo
from app.repo import LagerError

MAT_PREFIX = "mat:"


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    group: str
    fields: tuple[tuple[str, str, str], ...]  # (Schlüssel, Name, Einheit)
    options: dict[str, tuple[str, ...]]
    material: str = ""  # Profil (fil, cbl …) – dann stehen die Werte in item.specs


def _from_type(t: catalog.Type) -> Kind:
    return Kind(
        t.key, t.label, t.group,
        tuple((f.key, f.label, f.unit) for f in t.fields),
        {f.key: f.options for f in t.fields},
    )  # fmt: skip


def _from_material(profile: str) -> Kind:
    de = materials.MATERIALS[profile][0]
    fields = tuple((f.key, f.de, f.unit) for f in materials.FIELDS[profile])
    return Kind(MAT_PREFIX + profile, de, "Material & Datenblatt", fields, {}, profile)


def kinds(conn: sqlite3.Connection) -> list[Kind]:
    out = [_from_type(t) for _, types in catalog.grouped(conn) for t in types]
    return out + [_from_material(p) for p in materials.MATERIALS]


def kind(conn: sqlite3.Connection, key: str) -> Kind:
    if key.startswith(MAT_PREFIX) and key[len(MAT_PREFIX) :] in materials.MATERIALS:
        return _from_material(key[len(MAT_PREFIX) :])
    t = catalog.lookup(conn, key)
    if t is None:
        raise LagerError("Unbekannter Typ")
    return _from_type(t)


def kind_of_item(conn: sqlite3.Connection, item: sqlite3.Row) -> Kind | None:
    if item["ctype"]:
        t = catalog.lookup(conn, item["ctype"])
        return _from_type(t) if t else None
    if item["material"] in materials.MATERIALS:
        return _from_material(item["material"])
    return None


def values(item: sqlite3.Row, k: Kind) -> dict[str, str]:
    return materials.specs(item) if k.material else catalog.values_of(item)


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in conn.execute(
        "SELECT ctype, COUNT(*) n FROM item WHERE ctype IS NOT NULL AND archived = 0 GROUP BY ctype"
    ):
        out[r["ctype"]] = r["n"]
    for r in conn.execute(
        "SELECT material, COUNT(*) n FROM item WHERE ctype IS NULL AND material IS NOT NULL"
        " AND archived = 0 GROUP BY material"
    ):
        out[MAT_PREFIX + r["material"]] = r["n"]
    return out


def natural(value: str) -> tuple[Any, ...]:
    """„M2.5“ < „M3“ < „M10“, „8“ < „10“; Text danach alphabetisch."""
    parts = re.split(r"(\d+(?:[.,]\d+)?)", value.casefold())
    return tuple(
        (0, float(p.replace(",", "."))) if i % 2 else (1, p) for i, p in enumerate(parts) if p
    )


def items(
    conn: sqlite3.Connection, k: Kind, filters: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Teile des Typs mit Werten und Ort, gefiltert (Feld -> Wert), natürlich sortiert."""
    if k.material:
        rows = conn.execute(
            "SELECT * FROM item WHERE material = ? AND ctype IS NULL AND archived = 0",
            (k.material,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM item WHERE ctype = ? AND archived = 0", (k.key,)
        ).fetchall()
    want = {f: v.casefold() for f, v in (filters or {}).items() if v}
    out = []
    for r in rows:
        vals = values(r, k)
        if any(vals.get(f, "").casefold() != v for f, v in want.items()):
            continue
        out.append({**dict(r), "values": vals, "path": repo.path_label(conn, r["container_id"])})
    keys = [f for f, _, _ in k.fields]
    out.sort(key=lambda r: tuple(natural(r["values"].get(f, "~")) for f in keys) + (r["name"],))
    return out


def facets(k: Kind, rows: list[dict[str, Any]]) -> list[tuple[str, str, list[tuple[str, int]]]]:
    """Je Feld die vorkommenden Werte mit Anzahl (nur Felder mit mindestens einem Wert)."""
    out = []
    for key, label, _unit in k.fields:
        seen: dict[str, int] = {}
        for r in rows:
            if v := r["values"].get(key, ""):
                seen[v] = seen.get(v, 0) + 1
        if seen:
            out.append((key, label, sorted(seen.items(), key=lambda kv: natural(kv[0]))))
    return out


def default_axes(k: Kind, rows: list[dict[str, Any]]) -> tuple[str, str]:
    """Die zwei Felder mit den meisten verschiedenen Werten (mindestens 2) als Zeilen/Spalten."""
    scored = []
    for key, _label, _unit in k.fields:
        n = len({r["values"].get(key, "") for r in rows if r["values"].get(key)})
        scored.append((n, key))
    useful = [key for n, key in sorted(scored, key=lambda s: -s[0]) if n >= 1]
    keys = [f for f, _, _ in k.fields]
    row = useful[0] if useful else (keys[0] if keys else "")
    col = next((x for x in useful[1:] if x != row), next((x for x in keys if x != row), ""))
    return row, col


def raster(rows: list[dict[str, Any]], row: str, col: str) -> dict[str, Any]:
    """Variantenraster: Zeilen × Spalten, je Zelle Teile mit Summe und Orten."""
    rvals = sorted({r["values"].get(row, "") or "–" for r in rows}, key=natural)
    cvals = sorted({r["values"].get(col, "") or "–" for r in rows}, key=natural) if col else ["–"]
    cells: dict[str, dict[str, Any]] = {}
    for r in rows:
        rk = r["values"].get(row, "") or "–"
        ck = (r["values"].get(col, "") or "–") if col else "–"
        cell = cells.setdefault(f"{rk}\t{ck}", {"parts": [], "qty": 0, "uncounted": False})
        cell["parts"].append(r)
        if r["qty"] is None:
            cell["uncounted"] = True
        else:
            cell["qty"] += r["qty"]
    return {"rows": rvals, "cols": cvals, "cells": cells}


def untyped(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Teile ohne Typ (und ohne Material-Profil) mit Vorschlag aus dem Namen."""
    rows = conn.execute(
        "SELECT * FROM item WHERE ctype IS NULL AND material IS NULL AND archived = 0"
        " ORDER BY name COLLATE NOCASE LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        g = catalog.guess(conn, r["name"])
        out.append({**dict(r), "guess": g, "path": repo.path_label(conn, r["container_id"])})
    return out


def count_untyped(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM item WHERE ctype IS NULL AND material IS NULL AND archived = 0"
        ).fetchone()[0]
    )


def as_json(values_: dict[str, str]) -> str:
    return json.dumps(values_, ensure_ascii=False)
