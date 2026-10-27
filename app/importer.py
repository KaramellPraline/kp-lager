"""Import der Inventur-JSONs aus dem Haiku-Chat (Format: docs/HAIKU_PROMPT.md) und JSON-Export.

Vorschau = Import gegen eine In-Memory-Kopie der Datenbank, echte DB bleibt unberührt.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from app import codes as code_schema
from app import itemtypes, repo
from app.db import connect


@dataclass
class Report:
    containers_created: list[str] = field(default_factory=list)
    containers_moved: list[str] = field(default_factory=list)
    items_added: int = 0
    items_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse(text: str) -> list[dict[str, Any]]:
    """Akzeptiert ein Objekt, ein Array oder mehrere hintereinander eingefügte Antworten
    (auch mit ```json-Zäunen und Text dazwischen)."""
    text = re.sub(r"```(?:json)?", " ", text)
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    pos = 0
    while (m := re.compile(r"[\[{]").search(text, pos)) is not None:
        try:
            obj, end = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            pos = m.start() + 1
            continue
        found.extend(o for o in (obj if isinstance(obj, list) else [obj]) if isinstance(o, dict))
        pos = end
    return found


def _str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v).strip()


def validate(conn: sqlite3.Connection, data: list[dict[str, Any]], report: Report) -> None:
    codes = [_str(c.get("code")) for c in data]
    for raw in codes:
        norm = code_schema.normalize(raw) if raw else None
        if raw and (norm is None or norm.startswith(code_schema.ITEM_PREFIX)):
            report.errors.append(f"Code {raw} passt nicht zum Schema (z. B. EUR-001)")
    for i, c in enumerate(data, 1):
        label = f"Behälter {codes[i - 1] or '#' + str(i)}"
        if not codes[i - 1]:
            report.errors.append(f"{label}: 'code' fehlt")
        if not _str(c.get("name")):
            report.errors.append(f"{label}: 'name' fehlt")
        parent = _str(c.get("parent"))
        if parent and parent not in codes and not repo.get_container_by_code(conn, parent):
            report.errors.append(f"{label}: übergeordneter Code {parent} unbekannt")
        if parent and parent == codes[i - 1]:
            report.errors.append(f"{label}: ist sein eigener übergeordneter Behälter")
        for item in c.get("items") or []:
            if not isinstance(item, dict) or not _str(item.get("name")):
                report.errors.append(f"{label}: Item ohne Name")
            elif item.get("qty") is not None and not (
                isinstance(item["qty"], int) and item["qty"] >= 0
            ):
                report.errors.append(f"{label}: Menge von '{item['name']}' ungültig")
    dupes = {c for c in codes if c and codes.count(c) > 1}
    if dupes:
        report.errors.append(f"Codes mehrfach im Import: {', '.join(sorted(dupes))}")


def _slot_container(conn: sqlite3.Connection, parent_id: int, slot: str) -> int:
    row = conn.execute(
        "SELECT id FROM container WHERE parent_id = ? AND upper(position) = upper(?)",
        (parent_id, slot),
    ).fetchone()
    if row:
        return int(row["id"])
    return repo.create_container(conn, f"Fach {slot}", "fach", parent_id=parent_id, position=slot)


def apply(
    conn: sqlite3.Connection, data: list[dict[str, Any]], report: Report, review: bool = False
) -> None:
    pending = list(data)
    while pending:
        ready = [
            c
            for c in pending
            if not _str(c.get("parent")) or repo.get_container_by_code(conn, _str(c["parent"]))
        ]
        if not ready:
            report.errors.append(
                "Zirkuläre Eltern-Beziehung: " + ", ".join(_str(c["code"]) for c in pending)
            )
            return
        for c in ready:
            pending.remove(c)
            _apply_container(conn, c, report, review)


def _apply_container(
    conn: sqlite3.Connection, c: dict[str, Any], report: Report, review: bool = False
) -> None:
    code, name = _str(c["code"]), _str(c["name"])
    parent_code = _str(c.get("parent"))
    parent = repo.get_container_by_code(conn, parent_code) if parent_code else None
    parent_id = parent["id"] if parent else None
    kind = _str(c.get("kind")) or "sonstiges"
    if kind not in repo.KINDS:
        report.warnings.append(f"{code}: Art '{kind}' unbekannt → sonstiges")
        kind = "sonstiges"
    node = repo.get_container_by_code(conn, code)
    if node is None:
        grid = _str(c.get("grid")) or None
        cid = repo.create_container(conn, name, kind, parent_id=parent_id, code=code, grid=grid)
        report.containers_created.append(f"{code} {name}")
        if review:
            with conn:
                conn.execute("UPDATE container SET review = 1 WHERE id = ?", (cid,))
    else:
        cid = node["id"]
        if parent_code and node["parent_id"] != parent_id:
            repo.move_container(conn, cid, parent_id)
            report.containers_moved.append(f"{code} {node['name']}")
    for item in c.get("items") or []:
        target = cid
        if slot := _str(item.get("slot")):
            target = _slot_container(conn, cid, slot)
        iname = _str(item["name"])
        if any(i["name"].casefold() == iname.casefold() for i in repo.items_in(conn, target)):
            report.items_skipped += 1
            continue
        item_id = repo.add_item(
            conn,
            target,
            iname,
            qty=item.get("qty"),
            qty_hint=_str(item.get("qty_hint")),
            unit=_str(item.get("unit")),
            tags=_str(item.get("tags")),
            notes=_str(item.get("notes")),
            action="import",
            code=code_schema.new_item_code(conn),
        )
        extra: dict[str, str | int | None] = {}
        if full := _str(item.get("full_name")):
            extra["full_name"] = full
        if model := _str(item.get("model")):
            extra["model"] = model
        if type_name := _str(item.get("type")):
            extra["type_id"] = itemtypes.create(conn, type_name)  # neu oder vorhanden
        if review:
            extra["review"] = 1
        if extra:
            repo.update_item(conn, item_id, **extra)
        report.items_added += 1


def run(conn: sqlite3.Connection, text: str, commit: bool, review: bool = False) -> Report:
    """review=True: alles Angelegte bekommt das Flag „zu prüfen“ (KI-Ergebnisse)."""
    report = Report()
    data = parse(text)
    if not data:
        report.errors.append("Kein JSON-Objekt gefunden")
        return report
    for c in data:  # 'eur1' -> 'EUR-001'
        for key in ("code", "parent"):
            if (raw := _str(c.get(key))) and (norm := code_schema.normalize(raw)):
                c[key] = norm
    validate(conn, data, report)
    if report.errors:
        return report
    # Erst immer auf einer Kopie – so bleibt die echte DB bei Fehlern unverändert.
    scratch = connect(":memory:")
    conn.backup(scratch)
    apply(scratch, data, report, review)
    scratch.close()
    if commit and not report.errors:
        apply(conn, data, Report(), review)
    return report


def export(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Vollständiger Dump aller Tabellen (Backup/Portierung)."""
    return {
        table: [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        for table in ("container", "item", "event")
    }
