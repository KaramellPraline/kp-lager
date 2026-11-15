"""Kontext der gemeinsamen Formulare: Teil (`_teil_form.html`) und Behälter
(`_behaelter_form.html`) – einmal leer zum Anlegen, einmal vorbefüllt zum Bearbeiten."""

import sqlite3
from typing import Any

from fastapi import Request

from app import catalog, itemtypes, kinds, materials, presets, repo, typesettings
from app.catalog import Type
from app.web.shared import recent_targets

BASE_KEYS = (
    "name", "full_name", "qty", "unit", "qty_hint", "min_qty", "order_qty", "price", "order_url",
    "model", "datasheet_url", "expires", "opened", "tags", "notes", "type_id", "material",
)  # fmt: skip


def quick_types(conn: sqlite3.Connection, current: Type | None) -> list[Type]:
    """Chips über dem Formular (Handy): Favoriten und zuletzt genutzte Typen."""
    keys = sorted(catalog.favorite_keys(conn))
    rows = conn.execute(
        "SELECT ctype FROM item WHERE ctype IS NOT NULL"
        " GROUP BY ctype ORDER BY MAX(id) DESC LIMIT 8"
    ).fetchall()
    keys += [r["ctype"] for r in rows]
    if current is not None:
        keys.insert(0, current.key)
    out: list[Type] = []
    for k in dict.fromkeys(keys):
        t = catalog.lookup(conn, k)
        if t is not None:
            out.append(t)
    return out[:8]


def profiles() -> list[dict[str, Any]]:
    """Alle Eigenschafts-Profile mit ihren Feldern, gruppiert wie im Datenblatt."""
    out = []
    for key, (de, _en, prefix) in materials.MATERIALS.items():
        groups = []
        for g, labels in materials.GROUPS.items():
            fs = [f for f in materials.FIELDS[key] if f.group == g]
            if fs:
                groups.append((labels[0], fs))
        out.append({"key": key, "label": f"{de} ({prefix})", "groups": groups})
    return out


def teil(
    conn: sqlite3.Connection,
    request: Request,
    t: Type | None,
    *,
    item: sqlite3.Row | None = None,
    prefill: dict[str, str] | None = None,
    draft: bool = False,
    typ_url: str = "/neu?typ=",
) -> dict[str, Any]:
    """Alles, was `_teil_form.html` braucht. Ohne `item` = Anlegen, mit `item` = Bearbeiten."""
    key = t.key if t else ""
    required = typesettings.required_keys(conn, key) if t else set()
    kept = typesettings.kept_values(conn, key) if t and item is None else {}
    fields = t.fields if t else ()
    last_vals: dict[str, str] = {}
    if t:
        last_row = conn.execute(
            "SELECT * FROM item WHERE ctype = ? ORDER BY id DESC LIMIT 1", (key,)
        ).fetchone()
        last_vals = catalog.values_of(last_row) if last_row else {}
    values = dict(prefill if prefill is not None else kept)
    last = recent_targets(request)
    specs = materials.specs(item) if item is not None else {}
    fixed = catalog.profile_of(t)
    auto_name = catalog.name(t, values) if t else ""
    if item is not None:
        base = dict(item)
        base["name"] = "" if t and item["name"] == auto_name else item["name"]
        target = item["container_id"]
    else:
        base = dict.fromkeys(BASE_KEYS)
        target = last[0] if last else None
    tset = typesettings.get(conn, key) if t else {}
    return {
        "mode": "edit" if item is not None else "neu",
        "item": item,
        "ctype": t,
        "areas": catalog.areas(conn),
        "ctype_area": catalog.area_of(t) if t else "",
        "favs": catalog.favorite_keys(conn),
        "quick_types": quick_types(conn, t),
        "typ_url": typ_url,
        "prefill": values,
        "kept": kept,
        "last_vals": last_vals,
        "required": required,
        "sections": {
            "required": catalog.field_rows([f for f in fields if f.key in required]),
            "optional": catalog.field_rows(
                [f for f in fields if f.key not in required and not f.extra]
            ),
            "extra": catalog.field_rows([f for f in fields if f.key not in required and f.extra]),
        },
        "presets": presets.all_for(conn, key) if t else [],
        "opts": {f.key: catalog.options_for(conn, f, t) for f in fields},
        "draft": draft,
        "series_fields": [f for f in fields if catalog.options_for(conn, f, t)],
        "has_price_field": any(f.key == "price" for f in fields),
        "targets": repo.all_paths(conn),
        "target": target,
        "recent_targets": [
            {"id": p["id"], "label": repo.path_label(conn, p["id"])}
            for p in repo.containers_by_ids(conn, last)[:3]
        ],
        "fav_targets": [
            {"id": f["id"], "label": repo.path_label(conn, f["id"])}
            for f in repo.favorites(conn)[:10]
        ],
        "base": base,
        "auto_name": auto_name,
        "profile": fixed or (item["material"] if item is not None and item["material"] else ""),
        "profile_fixed": fixed,
        "profiles": profiles(),
        "covered": catalog.spec_keys(t) if t else set(),
        "specs": specs,
        "types": itemtypes.all_types(conn),
        "tset": tset,
    }


def behaelter(
    conn: sqlite3.Connection,
    request: Request,
    art: str,
    *,
    node: sqlite3.Row | None = None,
    art_url: str = "/neu/behaelter?art=",
) -> dict[str, Any]:
    """Alles, was `_behaelter_form.html` braucht. Ohne `node` = Anlegen."""
    offered = [(g, [k for k in ks if k not in ("compartment", "bin", "level")])
               for g, ks in kinds.KIND_GROUPS]  # fmt: skip
    if node is not None and node["kind"] in ("compartment", "bin", "level"):
        offered.append(("Fest", [node["kind"]]))
    last = recent_targets(request)
    targets = repo.all_paths(conn)
    if node is not None:  # nicht in sich selbst oder einen eigenen Unterbehälter
        inside = {r["id"] for r in conn.execute(
            "WITH RECURSIVE d(id) AS (SELECT ? UNION ALL SELECT c.id FROM container c"
            " JOIN d ON c.parent_id = d.id) SELECT id FROM d", (node["id"],))}  # fmt: skip
        targets = [p for p in targets if p["id"] not in inside]
    return {
        "mode": "edit" if node is not None else "neu",
        "node": node,
        "groups": [(g, ks) for g, ks in offered if ks],
        "art": art,
        "art_url": art_url,
        "targets": targets,
        "target": node["parent_id"] if node is not None else (last[0] if last else None),
    }
