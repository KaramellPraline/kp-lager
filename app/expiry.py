"""Ablauf-Erinnerung: Haltbarkeit (Harz, Kleber, Akkus …), „heute geöffnet“ mit Standard je Typ."""

import calendar
import contextlib
import sqlite3
from datetime import date, timedelta
from typing import Any

from app import repo, typesettings
from app.repo import LagerError

WARN_DAYS = 30


def add_months(day: date, months: int) -> date:
    m = day.month - 1 + months
    year, month = day.year + m // 12, m % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def due(
    conn: sqlite3.Connection, today: date | None = None, days: int = WARN_DAYS
) -> dict[str, list[dict[str, Any]]]:
    """Abgelaufen / läuft bald ab (innerhalb `days`), dringendste zuerst."""
    today = today or date.today()
    limit = (today + timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM item WHERE expires IS NOT NULL AND expires != '' AND expires <= ?"
        " AND archived = 0 ORDER BY expires",
        (limit,),
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {"expired": [], "soon": []}
    for r in rows:
        try:
            left = (date.fromisoformat(r["expires"]) - today).days
        except ValueError:
            continue
        entry = {**dict(r), "days": left, "path": repo.path_label(conn, r["container_id"])}
        out["expired" if left < 0 else "soon"].append(entry)
    return out


def opened_now(conn: sqlite3.Connection, item_id: int, today: date | None = None) -> str:
    """Geöffnet = heute; mit Standard-Haltbarkeit des Typs wird „haltbar bis“ gesetzt
    (nie später als ein schon eingetragenes Datum)."""
    today = today or date.today()
    item = repo.get_item(conn, item_id)
    months = typesettings.get(conn, typesettings.key_of(item))["shelf_months"]
    fields: dict[str, str | None] = {"opened": today.isoformat()}
    msg = "Als heute geöffnet markiert"
    if months:
        until = add_months(today, int(months)).isoformat()
        if not item["expires"] or until < item["expires"]:
            fields["expires"] = until
            msg += f" · haltbar bis {until}"
    repo.update_item(conn, item_id, **fields)
    return msg


def extend(conn: sqlite3.Connection, item_id: int, months: int, today: date | None = None) -> str:
    if months < 1:
        raise LagerError("Mindestens 1 Monat")
    item = repo.get_item(conn, item_id)
    base = today or date.today()
    if item["expires"]:
        with contextlib.suppress(ValueError):
            base = max(base, date.fromisoformat(item["expires"]))
    until = add_months(base, months).isoformat()
    repo.update_item(conn, item_id, expires=until)
    return f"Haltbar bis {until}"


def used_up(conn: sqlite3.Connection, item_id: int) -> str:
    item = repo.get_item(conn, item_id)
    repo.update_item(conn, item_id, archived=1)
    return f"„{item['name']}“ als verbraucht/entsorgt archiviert"
