"""Lagerwert: Menge × Preis je Behälter (inkl. aller Unterbehälter) und gesamt.

Teile ohne Menge zählen als 1 Stück (Kabel, Netzteile, Spulen); ohne Preis zählen sie nicht.
"""

import sqlite3


def euro(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def totals(conn: sqlite3.Connection) -> tuple[dict[int, float], dict[int, int]]:
    """({Behälter-ID: Wert inkl. darunter}, {Behälter-ID: Teile ohne Preis inkl. darunter})."""
    own: dict[int, float] = {}
    missing: dict[int, int] = {}
    for r in conn.execute(
        "SELECT container_id, SUM(COALESCE(qty, 1) * price) AS v,"
        " SUM(CASE WHEN price IS NULL THEN 1 ELSE 0 END) AS n"
        " FROM item WHERE archived = 0 GROUP BY container_id"
    ):
        own[r["container_id"]] = r["v"] or 0.0
        missing[r["container_id"]] = r["n"]
    parent = {r["id"]: r["parent_id"] for r in conn.execute("SELECT id, parent_id FROM container")}
    value: dict[int, float] = {}
    unpriced: dict[int, int] = {}
    for cid, v in own.items():
        node: int | None = cid
        while node is not None:
            value[node] = value.get(node, 0.0) + v
            unpriced[node] = unpriced.get(node, 0) + missing[cid]
            node = parent.get(node)
    return value, unpriced


def of_container(conn: sqlite3.Connection, container_id: int) -> tuple[float, int]:
    value, unpriced = totals(conn)
    return value.get(container_id, 0.0), unpriced.get(container_id, 0)


def total(conn: sqlite3.Connection) -> tuple[float, int]:
    row = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(qty, 1) * price), 0) AS v,"
        " COALESCE(SUM(CASE WHEN price IS NULL THEN 1 ELSE 0 END), 0) AS n"
        " FROM item WHERE archived = 0"
    ).fetchone()
    return float(row["v"]), int(row["n"])
