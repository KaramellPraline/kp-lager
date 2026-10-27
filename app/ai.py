"""Lokale KI über das Gateway (OpenAI-kompatibel): Diktate -> Einträge, Teile vervollständigen.

Alles, was die KI anlegt oder ändert, bekommt das Flag „zu prüfen“ (review) und erscheint unter
Mehr › Freigaben. Beim Vervollständigen wird der alte Stand in item.ai_backup gesichert.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app import datasheets, importer, itemtypes, prompt, repo
from app.repo import LagerError

ENRICH_FIELDS = ("name", "full_name", "model", "tags", "type_id", "datasheet_url")


def chat(url: str, token: str, model: str, messages: list[dict[str, str]]) -> str:
    """Eine Chat-Antwort holen (Dienste starten bei Bedarf -> großzügiges Timeout)."""
    if not url:
        raise LagerError("Keine lokale KI eingerichtet (LAGER_AI_URL)")
    try:
        with httpx.Client(timeout=600) as client:
            resp = client.post(
                f"{url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={"model": model, "messages": messages, "temperature": 0.2},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise LagerError(f"Lokale KI nicht erreichbar: {exc}") from None
    text = str(resp.json()["choices"][0]["message"]["content"])
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def entries_from_text(
    conn: sqlite3.Connection, url: str, token: str, model: str, text: str,
    code: str | None = None, name: str = "", kind: str = "",
) -> importer.Report:  # fmt: skip
    """Diktat/Notiz -> JSON vom lokalen Modell -> Import mit Flag „zu prüfen“."""
    types = itemtypes.names(conn)
    answer = chat(url, token, model, [
        {"role": "system", "content": prompt.local_system(types)},
        {"role": "user", "content": prompt.local_for_text(text, code, name, kind)},
    ])  # fmt: skip
    data = importer.parse(answer)
    if code:  # Behälter-Kontext: Code erzwingen, falls das Modell ihn weglässt
        for obj in data:
            obj.setdefault("code", code)
            if not obj.get("code"):
                obj["code"] = code
    payload = json.dumps([d for d in data if d.get("code")], ensure_ascii=False)
    if payload == "[]":
        report = importer.Report()
        report.errors.append("Die KI hat keine Behälter mit Code erkannt")
        return report
    return importer.run(conn, payload, commit=True, review=True)


def enrich_item(
    conn: sqlite3.Connection, url: str, token: str, model: str, item_id: int, sheet_dir: Path
) -> str:
    """Teil vervollständigen; alter Stand wird für „Ablehnen“ gesichert."""
    item = repo.get_item(conn, item_id)
    answer = chat(url, token, model, prompt.local_enrich(dict(item), itemtypes.names(conn)))
    found = importer.parse(answer)
    if not found:
        raise LagerError("Die KI hat keine verwertbare Antwort geliefert")
    sugg: dict[str, Any] = found[0]
    backup = {k: item[k] for k in ENRICH_FIELDS}
    changes: dict[str, str | int | None] = {}
    for key in ("name", "full_name", "model", "tags", "datasheet_url"):
        raw = sugg.get(key) or ""
        value = (" ".join(map(str, raw)) if isinstance(raw, list) else str(raw)).strip()
        if value and value != (item[key] or ""):
            changes[key] = value[:24] if key == "name" else value
    if type_name := str(sugg.get("type") or "").strip():
        type_id = itemtypes.create(conn, type_name)
        if type_id != item["type_id"]:
            changes["type_id"] = type_id
    if not changes:
        return "Die KI hatte nichts zu ergänzen"
    if item["ai_backup"] is None:  # bei mehrfachem Vervollständigen den Ursprung behalten
        changes["ai_backup"] = json.dumps(backup, ensure_ascii=False)
    changes["review"] = 1
    repo.update_item(conn, item_id, **changes)
    fields = ", ".join(k for k in changes if k not in ("review", "ai_backup"))
    msg = f"KI-Vorschlag übernommen ({fields})"
    if changes.get("datasheet_url") and not item["datasheet"]:
        try:
            stem = (
                f"{item['code'] or item_id}-{changes.get('model') or item['model'] or item['name']}"
            )
            name = datasheets.download(str(changes["datasheet_url"]), sheet_dir, stem)
            repo.update_item(conn, item_id, datasheet=name)
            msg += " · Datenblatt geladen"
        except LagerError:
            msg += " · Datenblatt-URL nicht ladbar"
    return msg + " – bitte unter Freigaben prüfen"


# --- Freigaben ------------------------------------------------------------------------


def pending(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    items = conn.execute(
        "SELECT i.*, t.name AS type_name FROM item i LEFT JOIN item_type t ON t.id = i.type_id"
        " WHERE i.review = 1 ORDER BY i.id DESC"
    ).fetchall()
    nodes = conn.execute("SELECT * FROM container WHERE review = 1 ORDER BY id DESC").fetchall()
    out_items = [
        {
            **dict(r),
            "path": repo.path_label(conn, r["container_id"]),
            "backup": json.loads(r["ai_backup"]) if r["ai_backup"] else None,
        }
        for r in items
    ]
    out_nodes = [{**dict(r), "path": repo.path_label(conn, r["id"])} for r in nodes]
    return {"items": out_items, "nodes": out_nodes}


def count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT (SELECT COUNT(*) FROM item WHERE review = 1)"
        " + (SELECT COUNT(*) FROM container WHERE review = 1)"
    ).fetchone()
    return int(row[0])


def approve_item(conn: sqlite3.Connection, item_id: int) -> None:
    repo.update_item(conn, item_id, review=0, ai_backup=None)


def reject_item(conn: sqlite3.Connection, item_id: int) -> str:
    """Neu angelegt -> löschen; vervollständigt -> alten Stand wiederherstellen."""
    item = repo.get_item(conn, item_id)
    if item["ai_backup"]:
        backup: dict[str, Any] = json.loads(item["ai_backup"])
        repo.update_item(conn, item_id, **backup, review=0, ai_backup=None)
        return f"Alter Stand von „{backup.get('name') or item['name']}“ wiederhergestellt"
    repo.delete_item(conn, item_id)
    return f"„{item['name']}“ verworfen"


def approve_node(conn: sqlite3.Connection, node_id: int) -> None:
    with conn:
        conn.execute("UPDATE container SET review = 0 WHERE id = ?", (node_id,))


def approve_all(conn: sqlite3.Connection) -> int:
    n = count(conn)
    with conn:
        conn.execute("UPDATE item SET review = 0, ai_backup = NULL WHERE review = 1")
        conn.execute("UPDATE container SET review = 0 WHERE review = 1")
    return n
