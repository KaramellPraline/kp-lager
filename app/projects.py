"""Projekte: Teileliste planen und im Lager per Scan systematisch einsammeln.

Einsammeln bucht eine Entnahme (7-Tage-Frist, stornierbar) – so stimmt der Bestand.
Die Liste ist nach Lagerort sortiert, damit man sie als Laufweg abarbeiten kann.
"""

import sqlite3
from typing import Any

from app import repo, withdrawals
from app.repo import LagerError, Row


def create(conn: sqlite3.Connection, name: str, notes: str = "") -> int:
    if not name.strip():
        raise LagerError("Projektname fehlt")
    with conn:
        cur = conn.execute("INSERT INTO project (name, notes) VALUES (?, ?)", (name.strip(), notes))
    assert cur.lastrowid is not None
    return cur.lastrowid


def get(conn: sqlite3.Connection, pid: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM project WHERE id = ?", (pid,)).fetchone()
    if row is None:
        raise LagerError("Projekt nicht gefunden")
    return row


def all_projects(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT p.*, COUNT(l.id) AS total, COALESCE(SUM(l.gathered), 0) AS done_lines"
        " FROM project p LEFT JOIN project_item l ON l.project_id = p.id"
        " GROUP BY p.id ORDER BY p.done, p.id DESC"
    ).fetchall()


def add_line(
    conn: sqlite3.Connection, pid: int, item_id: int | None, name: str = "", qty: int | None = None
) -> int:
    get(conn, pid)
    if item_id is not None:
        item = repo.get_item(conn, item_id)
        name = name or item["name"]
        dup = conn.execute(
            "SELECT id FROM project_item WHERE project_id = ? AND item_id = ?", (pid, item_id)
        ).fetchone()
        if dup:
            raise LagerError(f"„{name}“ steht schon auf der Liste")
    if not name.strip():
        raise LagerError("Was wird gebraucht?")
    with conn:
        cur = conn.execute(
            "INSERT INTO project_item (project_id, item_id, name, qty) VALUES (?, ?, ?, ?)",
            (pid, item_id, name.strip(), qty),
        )
    assert cur.lastrowid is not None
    return cur.lastrowid


def remove_line(conn: sqlite3.Connection, line_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM project_item WHERE id = ?", (line_id,))


def lines(conn: sqlite3.Connection, pid: int) -> list[dict[str, Any]]:
    """Zeilen mit Lagerort, sortiert als Laufweg (offen zuerst, dann nach Pfad)."""
    rows = conn.execute(
        "SELECT l.*, i.container_id, i.qty AS stock, i.unit, i.code"
        " FROM project_item l LEFT JOIN item i ON i.id = l.item_id WHERE l.project_id = ?",
        (pid,),
    ).fetchall()
    out = [
        {**dict(r), "path": repo.path_label(conn, r["container_id"]) if r["container_id"] else ""}
        for r in rows
    ]
    out.sort(key=lambda r: (r["gathered"], r["path"] == "", r["path"], r["name"].casefold()))
    return out


def gather(conn: sqlite3.Connection, line_id: int, take: bool = True) -> str:
    line = conn.execute("SELECT * FROM project_item WHERE id = ?", (line_id,)).fetchone()
    if line is None:
        raise LagerError("Eintrag nicht gefunden")
    if line["gathered"]:
        return f"„{line['name']}“ ist schon eingesammelt"
    if take and line["item_id"] is not None:
        withdrawals.take(
            conn, line["item_id"], line["qty"] or 1, note=f"Projekt #{line['project_id']}"
        )
    with conn:
        conn.execute(
            "UPDATE project_item SET gathered = 1, gathered_at = datetime('now') WHERE id = ?",
            (line_id,),
        )
    return f"„{line['name']}“ eingesammelt"


def gather_by_code(conn: sqlite3.Connection, pid: int, code: str) -> str:
    """Scan im Projekt: passende Zeile einsammeln; Teil nicht auf der Liste -> ergänzen."""
    item = repo.get_item_by_code(conn, code)
    if item is None:
        raise LagerError(f"{code} ist kein bekanntes Teil")
    line = conn.execute(
        "SELECT id FROM project_item WHERE project_id = ? AND item_id = ?", (pid, item["id"])
    ).fetchone()
    line_id = line["id"] if line else add_line(conn, pid, item["id"])
    return gather(conn, line_id)


def set_done(conn: sqlite3.Connection, pid: int, done: bool) -> None:
    with conn:
        conn.execute("UPDATE project SET done = ? WHERE id = ?", (int(done), pid))
