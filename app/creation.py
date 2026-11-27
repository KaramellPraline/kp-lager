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


# --- Anlegen nach Katalog-Typ (API/MCP): dieselben Regeln wie der Hinzufügen-Tab (/neu) --------

DUPLICATE_MODES = ("ask", "add", "new")


def _queue_labels(conn: sqlite3.Connection, item_ids: list[int], queue: bool | None) -> int:
    """Etiketten in die Warteschlange; None = wie der Druckmodus beim Anlegen (aus = nein)."""
    from app import labels  # spät: labels -> repo/codes

    if queue is None:
        mode = codes.get_setting(conn, "print_mode", "")
        if not mode:
            mode = "einzel" if codes.get_setting(conn, "auto_print", "0") == "1" else "aus"
        queue = mode != "aus"
    if not queue:
        return 0
    n = 0
    for item_id in item_ids:
        item = repo.get_item(conn, item_id)
        if item["code"] and not item["label_printed"]:
            labels.enqueue(conn, item["code"], *labels.item_texts(conn, item))
            n += 1
    return n


def add_from_catalog(
    conn: sqlite3.Connection,
    type_key: str,
    values: dict[str, Any],
    container_id: int,
    qty: int | None = None,
    count: int = 1,
    series_field: str = "",
    series: list[str] | None = None,
    on_duplicate: str = "ask",
    dry_run: bool = False,
    extra: dict[str, str] | None = None,
    label: bool = True,
    queue_labels: bool | None = None,
) -> dict[str, Any]:
    """Teil(e) nach Katalog-Typ anlegen: Name aus der Vorlage, Pflichtfelder, Reihe (mehrere Werte
    eines Feldes), Einzelstücke (je Stück ein Teil), Dubletten wie im Formular.

    Rückgabe: {"status": "created"|"updated"|"duplicate"|"preview", "created": [ids],
    "updated": [ids], "planned": [{name, fields, duplicates}]}. Bei "duplicate" wurde nichts
    geschrieben; erneut mit on_duplicate="add" (Menge dort erhöhen) oder "new" aufrufen."""
    from app import catalog, teilform, typesettings  # spät: catalog -> creation vermeiden

    t = catalog.lookup(conn, type_key.strip())
    if t is None:
        raise LagerError(f"Unbekannter Typ „{type_key}“ - gültige Schlüssel: GET /types/catalog")
    if on_duplicate not in DUPLICATE_MODES:
        raise LagerError(f"on_duplicate: {', '.join(DUPLICATE_MODES)}")
    keys = [f.key for f in t.fields]
    unknown = sorted(set(values) - set(keys))
    if unknown:
        raise LagerError(
            f"Unbekannte Felder für {t.key}: {', '.join(unknown)}. Gültig: {', '.join(keys)}"
        )
    vals = {k: catalog.number(str(values.get(k) or "")).strip() for k in keys}
    runs = [str(v).strip() for v in (series or []) if str(v).strip()]
    if runs and series_field not in vals:
        raise LagerError(f"series_field muss ein Feld von {t.key} sein: {', '.join(keys)}")
    required = typesettings.required_keys(conn, t.key)
    missing = [
        f.label for f in t.fields
        if f.key in required and not vals[f.key] and not (runs and f.key == series_field)
    ]  # fmt: skip
    if missing:
        raise LagerError("Pflichtfeld fehlt: " + ", ".join(missing))
    copies = 1
    if t.single:  # Einzelstücke: jedes Stück eigenes Teil mit eigenem Etikett
        copies = max(1, min(max(count, qty or 1), MAX_COUNT))
        qty = 1
    if runs and extra:  # eigener Name passt nicht zu einer Reihe
        extra = {k: v for k, v in extra.items() if k != "name"}
    variants = [{**vals, series_field: v} for v in runs] or [vals]
    planned = []
    for v in variants:
        name = catalog.name(t, v)
        if not name:
            raise LagerError(f"Bitte mindestens ein Feld für „{t.label}“ ausfüllen")
        dupes = [] if t.single or on_duplicate == "new" else catalog.duplicates(conn, t.key, v)
        dupes.sort(key=lambda r: r["container_id"] != container_id)  # gleicher Behälter zuerst
        planned.append((v, name, dupes))
    report = [
        {"name": n, "fields": {k: x for k, x in v.items() if x}, "copies": copies,
         "duplicates": [{"id": d["id"], "code": d["code"], "name": d["name"], "qty": d["qty"],
                         "path": repo.path_label(conn, d["container_id"])} for d in dupes]}
        for v, n, dupes in planned
    ]  # fmt: skip
    out: dict[str, Any] = {"type": t.key, "label": t.label, "created": [], "updated": [],
                           "planned": report}  # fmt: skip
    if dry_run:
        return {**out, "status": "preview"}
    if on_duplicate == "ask" and any(d for _v, _n, d in planned):
        return {**out, "status": "duplicate"}
    created: list[int] = []
    for v, _name, dupes in planned:
        if dupes:  # on_duplicate == "add": Menge beim vorhandenen Teil erhöhen
            d = dupes[0]
            if qty and d["qty"] is not None:
                repo.change_qty(conn, d["id"], qty, note="Nachgelegt (API)")
            elif qty and d["qty"] is None:
                repo.update_item(conn, d["id"], qty=qty)
            out["updated"].append(d["id"])
            continue
        for _ in range(copies):
            item_id = catalog.create(conn, t.key, v, container_id, qty, standalone=label)
            if extra:
                teilform.after_create(conn, item_id, t, extra)
            created.append(item_id)
    out["created"] = created
    out["labels_queued"] = _queue_labels(conn, created, queue_labels) if label else 0
    out["status"] = "created" if created else "updated"
    return out
