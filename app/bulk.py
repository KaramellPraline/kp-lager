"""Massenbearbeitung: viele Teile und Behälter auf einmal verschieben oder ändern.

Referenzen sind 'i<ID>' (Teil) und 'c<ID>' (Behälter), wie sie das Auswahlformular schickt.
"""

import sqlite3

from app import codes, itemtypes, labels, materials, repo
from app.repo import LagerError

# Aktion -> (Beschriftung, Eingabe: '' | 'target' | 'tag' | 'cat' | 'text' | 'number')
ACTIONS: dict[str, tuple[str, str]] = {
    "move": ("Verschieben nach …", "target"),
    "tag": ("Tag setzen …", "tag"),
    "cat": ("Kategorie ändern …", "cat"),
    "min": ("Mindestbestand setzen …", "number"),
    "unit": ("Einheit setzen …", "text"),
    "price": ("Preis setzen (€) …", "text"),
    "list_on": ("Auf Einkaufsliste", ""),
    "list_off": ("Von Einkaufsliste nehmen", ""),
    "label": ("Etiketten in Warteschlange", ""),
    "archive": ("Archivieren (ausblenden)", ""),
    "delete": ("Löschen (Behälter nur wenn leer)", ""),
}


def parse(refs: list[str]) -> tuple[list[int], list[int]]:
    items: list[int] = []
    nodes: list[int] = []
    for ref in refs:
        if len(ref) > 1 and ref[1:].isdigit() and ref[0] in "ic":
            (items if ref[0] == "i" else nodes).append(int(ref[1:]))
    return items, nodes


def apply(
    conn: sqlite3.Connection, refs: list[str], action: str, value: str = "", target: str = ""
) -> str:
    if action not in ACTIONS:
        raise LagerError("Bitte eine Aktion wählen")
    item_ids, node_ids = parse(refs)
    if not item_ids and not node_ids:
        raise LagerError("Nichts ausgewählt")
    n = 0
    if action == "move":
        if not target.isdigit() or repo.get_container(conn, int(target)) is None:
            raise LagerError("Bitte ein Ziel wählen")
        dest = int(target)
        for cid in node_ids:
            repo.move_container(conn, cid, dest)
            n += 1
        for iid in item_ids:
            repo.move_item(conn, iid, dest)
            n += 1
        return f"{n} verschoben → {repo.path_label(conn, dest)}"
    if action == "label":
        for iid in item_ids:
            it = repo.get_item(conn, iid)
            if it["code"]:
                labels.enqueue(conn, it["code"], it["name"], "")
                n += 1
        for cid in node_ids:
            c = repo.get_container(conn, cid)
            if c and c["code"]:
                text, extra = labels.container_label(conn, c)
                labels.enqueue(conn, c["code"], text, extra)
                n += 1
        return f"{n} Etiketten in der Warteschlange"
    if action == "delete":
        for iid in item_ids:
            repo.delete_item(conn, iid)
            n += 1
        for cid in node_ids:
            repo.delete_container(conn, cid)
            n += 1
        return f"{n} gelöscht"
    for iid in item_ids:
        if action == "tag":
            name = value.strip()
            repo.update_item(conn, iid, type_id=itemtypes.create(conn, name) if name else None)
        elif action == "cat":
            _change_cat(conn, iid, value.strip().upper())
        elif action == "min":
            num = value.strip()
            if num and not num.isdigit():
                raise LagerError("Mindestbestand: ganze Zahl (leer = keiner)")
            repo.update_item(conn, iid, min_qty=int(num) if num else None)
        elif action == "unit":
            repo.update_item(conn, iid, unit=value.strip())
        elif action == "price":
            repo.update_item(
                conn, iid, price=materials.parse_price(value) if value.strip() else None
            )
        elif action == "list_on":
            repo.update_item(conn, iid, on_list=1)
        elif action == "list_off":
            repo.update_item(conn, iid, on_list=0)
        elif action == "archive":
            repo.update_item(conn, iid, archived=1)
        n += 1
    return f"{n} Teile geändert"


def _change_cat(conn: sqlite3.Connection, item_id: int, cat: str) -> None:
    """Kategorie = Präfix des Teile-Codes: neuer Code, Etikett gilt als ungedruckt."""
    if cat not in codes.ITEM_PREFIXES:
        raise LagerError(f"Unbekannte Kategorie {cat}")
    item = repo.get_item(conn, item_id)
    if item["code"] and item["code"][:3] == cat:
        return
    new = codes.new_item_code(conn) if cat == codes.ITEM_PREFIX else codes.reserve(conn, cat, 1)[0]
    repo.set_item_code(conn, item_id, new)
    with conn:
        conn.execute(
            "UPDATE item SET material = ? WHERE id = ?",
            (materials.PREFIX_MATERIAL.get(cat), item_id),
        )
    if new and cat in repo.INDIVIDUAL:
        labels.enqueue(conn, new, item["name"], "")
