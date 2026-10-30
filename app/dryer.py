"""Filament-Trockner: Programme (Temperatur, Dauer) und Verlauf je Spule."""

import json
import sqlite3
from datetime import datetime, timedelta

from app.repo import LagerError

FMT = "%Y-%m-%d %H:%M:%S"


def programs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM dryer_program ORDER BY name").fetchall()


def add_program(
    conn: sqlite3.Connection, name: str, material: str, temp_c: float, hours: float, note: str = ""
) -> int:
    name = name.strip()
    if not name:
        raise LagerError("Programm braucht einen Namen")
    if not 30 <= temp_c <= 120:
        raise LagerError("Temperatur zwischen 30 und 120 °C")
    if not 0.5 <= hours <= 72:
        raise LagerError("Dauer zwischen 0,5 und 72 Stunden")
    with conn:
        cur = conn.execute(
            "INSERT INTO dryer_program (name, material, temp_c, hours, note) VALUES (?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET material = excluded.material,"
            " temp_c = excluded.temp_c, hours = excluded.hours, note = excluded.note",
            (name, material.strip(), temp_c, hours, note.strip()),
        )
    return int(cur.lastrowid or 0)


def delete_program(conn: sqlite3.Connection, program_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM dryer_program WHERE id = ?", (program_id,))


def start(conn: sqlite3.Connection, item_id: int, program_id: int, note: str = "") -> int:
    prog = conn.execute("SELECT * FROM dryer_program WHERE id = ?", (program_id,)).fetchone()
    item = conn.execute("SELECT material FROM item WHERE id = ?", (item_id,)).fetchone()
    if prog is None or item is None:
        raise LagerError("Programm oder Teil nicht gefunden")
    if item["material"] != "fil":
        raise LagerError("Trocknen gibt es nur für Filament")
    with conn:
        cur = conn.execute(
            "INSERT INTO dry_log (item_id, program, temp_c, hours, note) VALUES (?,?,?,?,?)",
            (item_id, prog["name"], prog["temp_c"], prog["hours"], note.strip()),
        )
    return int(cur.lastrowid or 0)


def mark_dried(conn: sqlite3.Connection, item_id: int, dryer: sqlite3.Row) -> str:
    """Scan Trockner-Etikett, dann Filament-Etikett: sofort als getrocknet (jetzt) vermerken."""
    item = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if item is None or item["material"] != "fil":
        raise LagerError("Trocknen gibt es nur für Filament")
    try:
        specs = json.loads(item["specs"] or "{}")
    except ValueError:
        specs = {}
    material = str(specs.get("material", "")).strip()
    prog = conn.execute(
        "SELECT * FROM dryer_program WHERE name = ? COLLATE NOCASE OR material = ? COLLATE NOCASE"
        " ORDER BY name = ? COLLATE NOCASE DESC LIMIT 1",
        (material, material, material),
    ).fetchone()
    temp = float(prog["temp_c"] if prog else specs.get("dry_temp", 0) or 0)
    hours = float(prog["hours"] if prog else specs.get("dry_hours", 0) or 0)
    stamp = datetime.now().strftime(FMT)
    with conn:
        conn.execute(
            "INSERT INTO dry_log (item_id, program, temp_c, hours, started_at, done_at, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item_id,
                prog["name"] if prog else "Scan",
                temp,
                hours,
                stamp,
                stamp,
                f"Trockner {dryer['name']} ({dryer['code'] or '–'}), per Scan",
            ),
        )
    return (
        f"„{item['name']}“ als getrocknet gespeichert ({stamp[8:10]}.{stamp[5:7]}. {stamp[11:16]})"
    )


def finish(conn: sqlite3.Connection, log_id: int) -> None:
    with conn:
        conn.execute(
            "UPDATE dry_log SET done_at = datetime('now', 'localtime')"
            " WHERE id = ? AND done_at IS NULL",
            (log_id,),
        )


def _decorate(r: sqlite3.Row, now: datetime) -> dict[str, object]:
    started = datetime.strptime(r["started_at"], FMT)
    ends = started + timedelta(hours=r["hours"])
    left = (ends - now).total_seconds()
    return {
        **dict(r),
        "ends_at": ends.strftime("%d.%m. %H:%M"),
        "ready": r["done_at"] is None and left <= 0,
        "left": ""
        if left <= 0 or r["done_at"]
        else f"noch {int(left // 3600)} h {int(left % 3600 // 60)} min",
        "running": r["done_at"] is None,
    }


def running(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict[str, object]]:
    now = now or datetime.now()
    rows = conn.execute(
        "SELECT d.*, i.name AS item_name, i.code AS item_code FROM dry_log d"
        " JOIN item i ON i.id = d.item_id WHERE d.done_at IS NULL ORDER BY d.started_at"
    ).fetchall()
    return [_decorate(r, now) for r in rows]


def history(
    conn: sqlite3.Connection,
    item_id: int | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    now = now or datetime.now()
    sql = (
        "SELECT d.*, i.name AS item_name, i.code AS item_code FROM dry_log d"
        " JOIN item i ON i.id = d.item_id"
    )
    args: tuple[object, ...] = ()
    if item_id is not None:
        sql += " WHERE d.item_id = ?"
        args = (item_id,)
    rows = conn.execute(sql + " ORDER BY d.started_at DESC, d.id DESC LIMIT ?", (*args, limit))
    return [_decorate(r, now) for r in rows.fetchall()]


def last_dried(conn: sqlite3.Connection, item_id: int) -> str:
    row = conn.execute(
        "SELECT COALESCE(done_at, started_at) AS t FROM dry_log WHERE item_id = ?"
        " ORDER BY started_at DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    return str(row["t"])[:10] if row else ""
