"""Bestellhistorie und Lieferanten: wo, wann, zu welchem Preis wurde ein Teil gekauft."""

import sqlite3
from typing import Any

from app import repo
from app.repo import LagerError, Row


def supplier_id(conn: sqlite3.Connection, name: str, url: str = "") -> int | None:
    """Lieferant per Name (ohne Groß-/Kleinschreibung) holen oder anlegen; leer = keiner."""
    name = name.strip()
    if not name:
        return None
    row = conn.execute("SELECT id, url FROM supplier WHERE name = ?", (name,)).fetchone()
    if row:
        if url and not row["url"]:
            with conn:
                conn.execute("UPDATE supplier SET url = ? WHERE id = ?", (url, row["id"]))
        return int(row["id"])
    with conn:
        cur = conn.execute("INSERT INTO supplier (name, url) VALUES (?, ?)", (name, url))
    assert cur.lastrowid is not None
    return cur.lastrowid


def add(
    conn: sqlite3.Connection,
    item_id: int,
    supplier: str = "",
    qty: int | None = None,
    price: float | None = None,
    bought_at: str = "",
    url: str = "",
    note: str = "",
) -> int:
    """Einkauf erfassen; der Stückpreis wird zum aktuellen Preis des Teils."""
    repo.get_item(conn, item_id)
    if qty is not None and qty < 1:
        raise LagerError("Menge mindestens 1")
    if price is not None and price < 0:
        raise LagerError("Preis darf nicht negativ sein")
    sid = supplier_id(conn, supplier)
    with conn:
        cur = conn.execute(
            "INSERT INTO purchase (item_id, supplier_id, qty, price, bought_at, url, note)"
            " VALUES (?, ?, ?, ?, COALESCE(NULLIF(?, ''), date('now', 'localtime')), ?, ?)",
            (item_id, sid, qty, price, bought_at, url.strip(), note.strip()),
        )
    if price is not None:
        repo.update_item(conn, item_id, price=price)
    assert cur.lastrowid is not None
    return cur.lastrowid


def delete(conn: sqlite3.Connection, purchase_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM purchase WHERE id = ?", (purchase_id,))


def for_item(conn: sqlite3.Connection, item_id: int) -> list[Row]:
    return conn.execute(
        "SELECT p.*, s.name AS supplier FROM purchase p"
        " LEFT JOIN supplier s ON s.id = p.supplier_id WHERE p.item_id = ?"
        " ORDER BY p.bought_at DESC, p.id DESC",
        (item_id,),
    ).fetchall()


def last_supplier(conn: sqlite3.Connection, item_id: int) -> str:
    row = conn.execute(
        "SELECT s.name FROM purchase p JOIN supplier s ON s.id = p.supplier_id"
        " WHERE p.item_id = ? ORDER BY p.bought_at DESC, p.id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    return str(row["name"]) if row else ""


def suppliers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT s.*, COUNT(p.id) AS n, COALESCE(SUM(p.price * COALESCE(p.qty, 1)), 0) AS total,"
        " MAX(p.bought_at) AS last FROM supplier s LEFT JOIN purchase p ON p.supplier_id = s.id"
        " GROUP BY s.id ORDER BY s.name COLLATE NOCASE"
    ).fetchall()
    return [dict(r) for r in rows]


def of_supplier(conn: sqlite3.Connection, sid: int) -> tuple[Row, list[Row]]:
    sup = conn.execute("SELECT * FROM supplier WHERE id = ?", (sid,)).fetchone()
    if sup is None:
        raise LagerError("Lieferant nicht gefunden")
    rows = conn.execute(
        "SELECT p.*, i.name AS item_name FROM purchase p JOIN item i ON i.id = p.item_id"
        " WHERE p.supplier_id = ? ORDER BY p.bought_at DESC, p.id DESC",
        (sid,),
    ).fetchall()
    return sup, rows


def update_supplier(conn: sqlite3.Connection, sid: int, url: str, note: str) -> None:
    with conn:
        conn.execute("UPDATE supplier SET url = ?, note = ? WHERE id = ?", (url.strip(), note, sid))


def names(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute("SELECT name FROM supplier ORDER BY name")]
