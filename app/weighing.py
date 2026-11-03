"""Zählen per Waage: Stückgewicht einmal ermitteln, danach Menge aus dem Gesamtgewicht."""

import sqlite3

from app import repo
from app.repo import LagerError


def _g(raw: str) -> float:
    try:
        value = float(raw.strip().replace(",", ".").removesuffix("g").strip())
    except ValueError:
        raise LagerError(f"„{raw}“ ist kein Gewicht in Gramm") from None
    if value < 0:
        raise LagerError("Gewicht darf nicht negativ sein")
    return value


def calibrate(
    conn: sqlite3.Connection, item_id: int, count: str, grams: str, tare: str = ""
) -> str:
    """N Stück wiegen (ggf. mit Behälter = Tara) -> Stückgewicht speichern."""
    n = int(count) if count.strip().isdigit() else 0
    if n < 1:
        raise LagerError("Anzahl der gewogenen Stücke angeben")
    t = _g(tare) if tare.strip() else 0.0
    net = _g(grams) - t
    if net <= 0:
        raise LagerError("Gewicht muss größer als das Leergewicht sein")
    unit = net / n
    repo.update_item(conn, item_id, unit_weight=round(unit, 4), tare=t)
    return f"Stückgewicht {unit:.3g} g gespeichert".replace(".", ",")


def estimate(item: sqlite3.Row, gross: str) -> int:
    if not item["unit_weight"]:
        raise LagerError("Erst das Stückgewicht ermitteln")
    net = _g(gross) - (item["tare"] or 0.0)
    return max(0, round(net / float(item["unit_weight"])))


def count(conn: sqlite3.Connection, item_id: int, gross: str) -> str:
    """Gesamtgewicht -> Menge setzen (als Buchung „Waage“)."""
    item = repo.get_item(conn, item_id)
    qty = estimate(item, gross)
    if item["qty"] is None:
        repo.update_item(conn, item_id, qty=qty)
    elif qty != item["qty"]:
        repo.change_qty(conn, item_id, qty - item["qty"], note="Waage")
    return f"Gewogen: {qty} Stück"
