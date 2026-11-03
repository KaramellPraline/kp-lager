"""Vollexport (`/export.json`: container, item, event) in den aktuellen Bestand übernehmen.

Zusammenführen statt überschreiben: Behälter und Teile werden über ihren Code wiedererkannt,
alles Fehlende kommt dazu. Danach passt `normalize` den Bestand an die aktuelle Struktur an:
fehlende Codes werden dynamisch vergeben, die Zähler neu aus dem Bestand gesetzt und Teile
anhand ihres Namens einem Typ zugeordnet.
"""

import json
import re
import sqlite3
from typing import Any

from app import catalog, codes, labels, repo
from app.importer import Report

TABLES = ("container", "item", "event")


def parse_dump(text: str) -> dict[str, list[dict[str, Any]]] | None:
    """Der Text ist ein Vollexport (Objekt mit container und item) – sonst None."""
    cleaned = re.sub(r"```(?:json)?", " ", text).strip()
    if not cleaned.startswith("{"):
        return None
    try:
        obj = json.loads(cleaned)
    except ValueError:
        return None
    if not (isinstance(obj, dict) and isinstance(obj.get("container"), list)
            and isinstance(obj.get("item"), list)):  # fmt: skip
        return None
    return {t: [r for r in obj.get(t, []) if isinstance(r, dict)] for t in TABLES}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _insert(conn: sqlite3.Connection, table: str, row: dict[str, Any], cols: set[str]) -> int:
    data = {k: v for k, v in row.items() if k in cols and k != "id"}
    names = ", ".join(data)
    marks = ", ".join("?" * len(data))
    with conn:
        cur = conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(data.values()))
    assert cur.lastrowid is not None
    return cur.lastrowid


def _code(raw: Any) -> str | None:
    """Schema-Code oder None (leer/ungültig -> wird später dynamisch vergeben)."""
    return codes.normalize(str(raw)) if raw else None


def merge(conn: sqlite3.Connection, dump: dict[str, list[dict[str, Any]]], report: Report) -> None:
    ccols, icols, ecols = (_columns(conn, t) for t in TABLES)
    cmap: dict[Any, int] = {}
    inbox_row = conn.execute("SELECT value FROM meta WHERE key = 'inbox_id'").fetchone()
    pending = list(dump["container"])
    rounds = 0
    while pending and rounds < 50:
        rounds += 1
        rest = []
        for c in pending:
            old_parent = c.get("parent_id")
            if old_parent is not None and old_parent not in cmap:
                if any(p.get("id") == old_parent for p in pending):
                    rest.append(c)  # Elternteil kommt noch
                    continue
                old_parent = None  # Elternteil fehlt im Export -> oberste Ebene
            parent = cmap.get(old_parent) if old_parent is not None else None
            code = _code(c.get("code"))
            found = repo.get_container_by_code(conn, code) if code else None
            if found is None:  # ohne Code: gleicher Name an gleicher Stelle
                row = conn.execute(
                    "SELECT * FROM container WHERE name = ? AND kind = ? AND parent_id IS ?",
                    (c.get("name"), c.get("kind"), parent),
                ).fetchone()
                found = row if row and not (row["code"] and code and row["code"] != code) else None
            if found is not None:
                cmap[c["id"]] = found["id"]
                if code and not found["code"] and not repo.get_container_by_code(conn, code):
                    repo.assign_code(conn, found["id"], code)
                continue
            data = {**c, "code": code, "parent_id": parent}
            new_id = _insert(conn, "container", data, ccols)
            cmap[c["id"]] = new_id
            report.containers_created.append(str(c.get("name")))
        pending = rest
    for c in pending:  # Zyklen o. Ä.: als oberste Ebene anlegen
        cmap[c["id"]] = _insert(conn, "container", {**c, "code": _code(c.get("code")),
                                                    "parent_id": None}, ccols)  # fmt: skip
        report.warnings.append(f"Behälter „{c.get('name')}“: Zuordnung unklar, oberste Ebene")
    _ = inbox_row

    imap: dict[Any, int] = {}
    for i in dump["item"]:
        dest = cmap.get(i.get("container_id"))
        if dest is None:
            dest = repo.inbox(conn)
            report.warnings.append(
                f"„{i.get('name')}“: Behälter fehlt im Export, nach „Zu sortieren“"
            )
        code = _code(i.get("code"))
        dup = repo.get_item_by_code(conn, code) if code else None
        if dup is None and not code:
            dup = conn.execute(
                "SELECT * FROM item WHERE name = ? AND container_id = ?", (i.get("name"), dest)
            ).fetchone()
        if dup is not None:
            imap[i["id"]] = dup["id"]
            report.items_skipped += 1
            continue
        data = {**i, "code": code, "container_id": dest, "type_id": None}
        imap[i["id"]] = _insert(conn, "item", data, icols)
        report.items_added += 1

    seen = {
        (r["ts"], r["action"], r["item_name"], r["note"])
        for r in conn.execute("SELECT ts, action, item_name, note FROM event")
    }
    for e in dump["event"]:
        key = (e.get("ts"), e.get("action"), e.get("item_name"), e.get("note"))
        if key in seen:
            continue
        seen.add(key)
        data = {
            **e,
            "item_id": imap.get(e.get("item_id")),
            "container_id": cmap.get(e.get("container_id")),
            "prev_container_id": cmap.get(e.get("prev_container_id")),
        }
        _insert(conn, "event", data, ecols)
        report.events_added += 1


def assign_missing_codes(conn: sqlite3.Connection, report: Report) -> None:
    """Behälter ohne Code bekommen einen aus dem Präfix ihrer Art, Teile einen ART-Code.

    Neue Codes landen mit ihrem Etikett in der Druck-Warteschlange.
    """
    for c in conn.execute(
        "SELECT * FROM container WHERE code IS NULL AND kind != 'compartment' ORDER BY id"
    ).fetchall():
        prefix = codes.KIND_PREFIX.get(c["kind"])
        if not prefix:
            continue
        code = codes.reserve(conn, prefix, 1)[0]
        repo.assign_code(conn, c["id"], code)
        fresh = repo.get_container(conn, c["id"])
        assert fresh is not None
        labels.enqueue(conn, code, *labels.container_label(conn, fresh))
        report.codes_assigned += 1
    if codes.auto_item_code(conn):
        for i in conn.execute("SELECT * FROM item WHERE code IS NULL ORDER BY id").fetchall():
            code = codes.reserve(conn, codes.ITEM_PREFIX, 1)[0]
            repo.set_item_code(conn, i["id"], code)
            labels.enqueue(conn, code, *labels.item_texts(conn, repo.get_item(conn, i["id"])))
            report.codes_assigned += 1


def auto_type(conn: sqlite3.Connection, report: Report, min_score: int = 6) -> None:
    """Teile ohne Typ anhand des Namens zuordnen, wenn die Erkennung sicher genug ist."""
    rows = conn.execute(
        "SELECT * FROM item WHERE ctype IS NULL AND material IS NULL AND archived = 0"
    ).fetchall()
    for r in rows:
        guess = catalog.guess(conn, r["name"])
        if guess and guess[2] >= min_score:
            catalog.set_fields(conn, r["id"], guess[0], guess[1], rename=False)
            report.typed += 1


def adopt_inbox(conn: sqlite3.Connection) -> None:
    """Hat der Export einen „Zu sortieren“-Behälter und ist noch keiner als Eingang gesetzt,
    wird er der Eingang (sonst legt die App später einen zweiten an)."""
    if conn.execute("SELECT 1 FROM meta WHERE key = 'inbox_id'").fetchone():
        return
    row = conn.execute(
        "SELECT id FROM container WHERE name = ? AND parent_id IS NULL ORDER BY id LIMIT 1",
        (repo.INBOX_NAME,),
    ).fetchone()
    if row:
        with conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('inbox_id', ?)", (str(row["id"]),))


def normalize(conn: sqlite3.Connection, report: Report) -> None:
    """An die aktuelle Struktur anpassen: Codes, Zähler, Typen – alles dynamisch."""
    adopt_inbox(conn)
    assign_missing_codes(conn, report)
    codes.sync_counters(conn)
    auto_type(conn, report)


def restore(conn: sqlite3.Connection, dump: dict[str, list[dict[str, Any]]]) -> Report:
    report = Report()
    merge(conn, dump, report)
    normalize(conn, report)
    report.restored = True
    return report
