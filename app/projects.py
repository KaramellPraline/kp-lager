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
            "UPDATE project_item SET gathered = 1, gathered_at = datetime('now'), reserved = 0"
            " WHERE id = ?",
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
    if done:
        release(conn, pid)


def reserved_elsewhere(conn: sqlite3.Connection, item_id: int, pid: int | None = None) -> int:
    """Von offenen Projekten (außer `pid`) reservierte, noch nicht geholte Menge eines Teils."""
    row = conn.execute(
        "SELECT COALESCE(SUM(l.reserved), 0) FROM project_item l"
        " JOIN project p ON p.id = l.project_id"
        " WHERE l.item_id = ? AND l.gathered = 0 AND p.done = 0 AND (? IS NULL OR p.id != ?)",
        (item_id, pid, pid),
    ).fetchone()
    return int(row[0])


def reservations(conn: sqlite3.Connection, item_id: int) -> list[Row]:
    return conn.execute(
        "SELECT p.id, p.name, l.reserved FROM project_item l JOIN project p ON p.id = l.project_id"
        " WHERE l.item_id = ? AND l.reserved > 0 AND l.gathered = 0 AND p.done = 0 ORDER BY p.name",
        (item_id,),
    ).fetchall()


def compare(conn: sqlite3.Connection, pid: int) -> dict[str, Any]:
    """Stückliste gegen den Bestand: je Zeile ok / teil (zu wenig) / fehlt (nicht im Lager).

    Was andere offene Projekte reserviert haben, steht diesem Projekt nicht zur Verfügung.
    """
    out = []
    cost = 0.0
    for line in lines(conn, pid):
        free: int | None = None
        if line["gathered"]:
            status, short = "geholt", 0
        elif line["item_id"] is None:
            status, short = "fehlt", int(line["qty"] or 1)
        else:
            need, stock = int(line["qty"] or 1), line["stock"]
            if stock is None:
                short = 0
            else:
                free = max(0, stock - reserved_elsewhere(conn, line["item_id"], pid))
                short = max(0, need - free)
            status = "ok" if short == 0 else ("teil" if free else "fehlt")
        price = conn.execute("SELECT price FROM item WHERE id = ?", (line["item_id"],)).fetchone()
        if short and price and price["price"] is not None:
            cost += float(price["price"]) * short
        out.append({**line, "status": status, "short": short, "free": free})
    counts = {s: sum(1 for r in out if r["status"] == s) for s in ("ok", "teil", "fehlt", "geholt")}
    return {
        "lines": out,
        "counts": counts,
        "cost": cost,
        "complete": not (counts["teil"] + counts["fehlt"]),
        "reserved": sum(1 for r in out if r["reserved"]),
    }


def reserve(conn: sqlite3.Connection, pid: int) -> int:
    """Verfügbares für offene Zeilen reservieren (höchstens den Bedarf); gibt die Zeilenzahl."""
    n = 0
    for line in compare(conn, pid)["lines"]:
        if line["gathered"] or line["item_id"] is None:
            continue
        need = int(line["qty"] or 1)
        amount = need if line["free"] is None else min(need, line["free"])
        with conn:
            conn.execute("UPDATE project_item SET reserved = ? WHERE id = ?", (amount, line["id"]))
        n += 1 if amount else 0
    return n


def release(conn: sqlite3.Connection, pid: int) -> None:
    with conn:
        conn.execute("UPDATE project_item SET reserved = 0 WHERE project_id = ?", (pid,))


def to_shopping(conn: sqlite3.Connection, pid: int) -> int:
    """Fehlmengen bekannter Teile auf die Einkaufsliste (Wunschmenge = Fehlmenge)."""
    n = 0
    for line in compare(conn, pid)["lines"]:
        if line["item_id"] is not None and line["short"]:
            repo.update_item(conn, line["item_id"], on_list=1, order_qty=line["short"])
            n += 1
    return n
