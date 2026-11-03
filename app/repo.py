"""Datenzugriff: Behälter-Baum, Items und Protokoll. Alle Funktionen committen selbst."""

import sqlite3
from string import ascii_uppercase
from typing import Any

Row = sqlite3.Row

# Gültige Arten; füllt app/kinds (feste + eigene, zur Laufzeit aktuell)
KINDS: list[str] = []
# Einzelstücke (Kabel, Netzteile): keine Menge, jedes Stück bekommt ein eigenes Etikett
INDIVIDUAL = ("CBL", "PSU")
METER_UNITS = ("m", "cm", "meter")  # Meterware zählt in Metern, nicht in Stück


class LagerError(ValueError):
    """Fachlicher Fehler (z. B. Bestand < 0, Behälter in sich selbst verschieben)."""


# --- Behälter -----------------------------------------------------------------


def parse_grid(grid: str) -> list[str]:
    """'4x3' (Spalten x Zeilen) -> ['A1', 'A2', 'A3', 'A4', 'B1', …, 'C4']."""
    try:
        cols, rows = (int(p) for p in grid.lower().split("x"))
    except ValueError:
        raise LagerError(f"Raster '{grid}' ungültig, erwartet z. B. '6x8'") from None
    if not (1 <= cols <= 30 and 1 <= rows <= len(ascii_uppercase)):
        raise LagerError(f"Raster '{grid}' außerhalb 1-30 Spalten / 1-26 Zeilen")
    return [f"{ascii_uppercase[r]}{c + 1}" for r in range(rows) for c in range(cols)]


def create_container(
    conn: sqlite3.Connection,
    name: str,
    kind: str,
    parent_id: int | None = None,
    code: str | None = None,
    position: str | None = None,
    grid: str | None = None,
    notes: str = "",
    size: str | None = None,
    model: str | None = None,
    dims: str = "",
    airtight: bool = False,
) -> int:
    """Legt einen Behälter an. Mit `grid` werden die Fächer als Kind-Behälter erzeugt."""
    from app.kinds import resolve  # spät: kinds importiert repo

    kind = resolve(kind) or kind
    if kind not in KINDS:
        raise LagerError(f"Unbekannte Art '{kind}'")
    slots = parse_grid(grid) if grid else []
    with conn:
        cur = conn.execute(
            "INSERT INTO container (code, parent_id, kind, name, position, grid, notes, size,"
            " model, dims, airtight) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (code, parent_id, kind, name, position, grid, notes, size, model, dims, int(airtight)),
        )
        cid = cur.lastrowid
        assert cid is not None
        conn.executemany(
            "INSERT INTO container (parent_id, kind, name, position)"
            " VALUES (?, 'compartment', ?, ?)",
            [(cid, f"Fach {s}", s) for s in slots],
        )
    return cid


def get_container(conn: sqlite3.Connection, container_id: int) -> Row | None:
    row: Row | None = conn.execute(
        "SELECT * FROM container WHERE id = ?", (container_id,)
    ).fetchone()
    return row


def get_container_by_code(conn: sqlite3.Connection, code: str) -> Row | None:
    row: Row | None = conn.execute("SELECT * FROM container WHERE code = ?", (code,)).fetchone()
    return row


def children(conn: sqlite3.Connection, container_id: int | None) -> list[Row]:
    """Direkte Unterbehälter; `None` = oberste Ebene (Räume)."""
    """Direkte Unterbehälter mit Item-Anzahl (`n_items`) und Item-Namen (`item_names`)."""
    return conn.execute(
        """
        SELECT c.*, COUNT(i.id) AS n_items, COALESCE(GROUP_CONCAT(i.name, ', '), '') AS item_names
        FROM container c LEFT JOIN item i ON i.container_id = c.id
        WHERE c.parent_id IS ?
        GROUP BY c.id
        ORDER BY CASE WHEN c.kind = 'compartment' THEN printf('%09d', c.id) ELSE lower(c.name) END
        """,
        (container_id,),
    ).fetchall()


def all_paths(conn: sqlite3.Connection) -> list[Row]:
    """Alle Behälter außer Fächern als (id, label) mit vollem Pfad – für Auswahllisten."""
    return conn.execute(
        """
        WITH RECURSIVE t(id, label, kind) AS (
            SELECT id, name, kind FROM container WHERE parent_id IS NULL
            UNION ALL
            SELECT c.id, t.label || ' › ' || c.name, c.kind
            FROM container c JOIN t ON c.parent_id = t.id
        )
        SELECT id, label FROM t WHERE kind != 'compartment' ORDER BY lower(label)
        """
    ).fetchall()


def update_container(conn: sqlite3.Connection, container_id: int, name: str, notes: str) -> None:
    with conn:
        conn.execute(
            "UPDATE container SET name = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
            (name.strip(), notes, container_id),
        )


def set_container_photo(conn: sqlite3.Connection, container_id: int, photo: str | None) -> None:
    with conn:
        conn.execute(
            "UPDATE container SET photo = ?, updated_at = datetime('now') WHERE id = ?",
            (photo, container_id),
        )


def delete_container(conn: sqlite3.Connection, container_id: int) -> int | None:
    """Löscht Behälter samt leerer Unterbehälter (z. B. Fächer); gibt Eltern-ID zurück."""
    subtree = conn.execute(
        """
        WITH RECURSIVE down(id, depth) AS (
            SELECT id, 0 FROM container WHERE id = ?
            UNION ALL
            SELECT c.id, depth + 1 FROM container c JOIN down ON c.parent_id = down.id
        )
        SELECT id FROM down ORDER BY depth DESC
        """,
        (container_id,),
    ).fetchall()
    ids = [r["id"] for r in subtree]
    marks = ",".join("?" * len(ids))
    if conn.execute(f"SELECT 1 FROM item WHERE container_id IN ({marks})", ids).fetchone():
        raise LagerError("Behälter ist nicht leer")
    if any(c["kind"] != "compartment" for c in children(conn, container_id)):
        raise LagerError("Behälter enthält noch Unterbehälter")
    parent = get_container(conn, container_id)
    with conn:
        conn.executemany("DELETE FROM container WHERE id = ?", [(i,) for i in ids])
        conn.execute(
            "INSERT INTO event (action, note) VALUES ('delete', ?)",
            (f"Behälter {parent['name'] if parent else container_id}",),
        )
    return parent["parent_id"] if parent else None


def container_path(conn: sqlite3.Connection, container_id: int) -> list[Row]:
    """Pfad von der Wurzel bis zum Behälter selbst, z. B. Keller › Regal 1 › Box 0042 › Fach B3."""
    rows = conn.execute(
        """
        WITH RECURSIVE up(id, parent_id, depth) AS (
            SELECT id, parent_id, 0 FROM container WHERE id = ?
            UNION ALL
            SELECT c.id, c.parent_id, up.depth + 1 FROM container c JOIN up ON c.id = up.parent_id
        )
        SELECT c.* FROM up JOIN container c ON c.id = up.id ORDER BY up.depth DESC
        """,
        (container_id,),
    ).fetchall()
    return rows


def path_label(conn: sqlite3.Connection, container_id: int) -> str:
    return " › ".join(r["name"] for r in container_path(conn, container_id))


def move_container(conn: sqlite3.Connection, container_id: int, new_parent_id: int | None) -> None:
    """Behälter umziehen (z. B. Kiste aus dem Stapel ins Regal). Verhindert Zyklen."""
    if new_parent_id is not None and any(
        r["id"] == container_id for r in container_path(conn, new_parent_id)
    ):
        raise LagerError("Behälter kann nicht in sich selbst oder einen Unterbehälter")
    node = get_container(conn, container_id)
    if node is None:
        raise LagerError("Behälter existiert nicht")
    target = get_container(conn, new_parent_id) if new_parent_id else None
    with conn:
        conn.execute(
            "UPDATE container SET parent_id = ?, position = NULL, updated_at = datetime('now')"
            " WHERE id = ?",
            (new_parent_id, container_id),
        )
        # prev_container_id 0 = vorher oberste Ebene
        conn.execute(
            "INSERT INTO event (item_name, container_id, prev_container_id, action, note)"
            " VALUES (?, ?, ?, 'move', ?)",
            (
                node["name"],
                container_id,
                node["parent_id"] or 0,
                f"nach {target['name'] if target else 'oberste Ebene'}",
            ),
        )


def assign_code(conn: sqlite3.Connection, container_id: int, code: str | None) -> None:
    """Etikett nachträglich zuordnen (z. B. Sortierkasten bekommt QR)."""
    with conn:
        conn.execute(
            "UPDATE container SET code = ?, label_printed = 0, updated_at = datetime('now')"
            " WHERE id = ?",
            (code, container_id),
        )


# --- Items ----------------------------------------------------------------------


def _log(
    conn: sqlite3.Connection,
    item: Row,
    action: str,
    delta: int | None = None,
    note: str = "",
    prev_container_id: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO event (item_id, item_name, container_id, prev_container_id, action, delta,"
        " note) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item["id"], item["name"], item["container_id"], prev_container_id, action, delta, note),
    )


def last_event_id(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM event").fetchone()[0])


def get_item(conn: sqlite3.Connection, item_id: int) -> Row:
    row: Row | None = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise LagerError(f"Item {item_id} existiert nicht")
    return row


def add_item(
    conn: sqlite3.Connection,
    container_id: int,
    name: str,
    qty: int | None = None,
    qty_hint: str = "",
    unit: str = "",
    tags: str = "",
    notes: str = "",
    action: str = "add",
    code: str | None = None,
) -> int:
    if qty is not None and qty < 0:
        raise LagerError("Menge darf nicht negativ sein")
    if code and code[:3] in INDIVIDUAL and unit.casefold() not in METER_UNITS:
        qty, qty_hint, unit = None, "", ""  # Kabel/Netzteile sind Einzelstücke (Meterware nicht)
    with conn:
        cur = conn.execute(
            "INSERT INTO item (container_id, name, qty, qty_hint, unit, tags, notes, code)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (container_id, name.strip(), qty, qty_hint, unit, tags, notes, code),
        )
        item_id = cur.lastrowid
        assert item_id is not None
        _log(conn, get_item(conn, item_id), action, qty)
    return item_id


def get_item_by_code(conn: sqlite3.Connection, code: str) -> Row | None:
    row: Row | None = conn.execute("SELECT * FROM item WHERE code = ?", (code,)).fetchone()
    return row


def set_item_code(conn: sqlite3.Connection, item_id: int, code: str | None) -> None:
    """Etikett-Code setzen/entfernen; neuer Code gilt als noch nicht gedruckt."""
    item = get_item(conn, item_id)
    with conn:
        conn.execute(
            "UPDATE item SET code = ?, label_printed = 0, updated_at = datetime('now')"
            " WHERE id = ?",
            (code, item_id),
        )
        _log(conn, item, "edit", note=f"Code {code or 'entfernt'}")


def items_in(conn: sqlite3.Connection, container_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM item WHERE container_id = ? AND archived = 0 ORDER BY name",
        (container_id,),
    ).fetchall()


def change_qty(conn: sqlite3.Connection, item_id: int, delta: int, note: str = "") -> int | None:
    """Entnehmen (delta < 0) / Einlagern (delta > 0). Ungezählte Items: nur Protokoll."""
    item = get_item(conn, item_id)
    new_qty = item["qty"]
    if new_qty is not None:
        new_qty += delta
        if new_qty < 0:
            raise LagerError(f"Nur {item['qty']} vorhanden")
    with conn:
        conn.execute(
            "UPDATE item SET qty = ?, updated_at = datetime('now') WHERE id = ?",
            (new_qty, item_id),
        )
        _log(conn, item, "take" if delta < 0 else "put", delta, note)
    return new_qty  # type: ignore[no-any-return]


def move_item(conn: sqlite3.Connection, item_id: int, container_id: int) -> None:
    item = get_item(conn, item_id)
    target = get_container(conn, container_id)
    if target is None:
        raise LagerError("Ziel-Behälter existiert nicht")
    with conn:
        conn.execute(
            "UPDATE item SET container_id = ?, updated_at = datetime('now') WHERE id = ?",
            (container_id, item_id),
        )
        _log(
            conn,
            item,
            "move",
            note=f"nach {target['name']}",
            prev_container_id=item["container_id"],
        )


def update_item(conn: sqlite3.Connection, item_id: int, **fields: str | int | float | None) -> None:
    allowed = {
        "name", "qty", "qty_hint", "unit", "tags", "notes", "photo", "min_qty", "on_list",
        "full_name", "type_id", "model", "datasheet_url", "datasheet", "review", "archived",
        "ai_backup", "order_url", "price", "specs", "ai_checked", "opened", "expires",
        "ordered_at", "order_qty", "unit_weight", "tare",
    }  # fmt: skip
    if not fields or not set(fields) <= allowed:
        raise LagerError(f"Erlaubte Felder: {sorted(allowed)}")
    item = get_item(conn, item_id)
    sets = ", ".join(f"{k} = ?" for k in fields)
    with conn:
        conn.execute(
            f"UPDATE item SET {sets}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), item_id),
        )
        _log(conn, item, "edit", note=", ".join(fields))


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    item = get_item(conn, item_id)
    with conn:
        _log(conn, item, "delete")
        conn.execute("DELETE FROM item WHERE id = ?", (item_id,))


def history(conn: sqlite3.Connection, item_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM event WHERE item_id = ? ORDER BY id DESC", (item_id,)
    ).fetchall()


SEARCH_TEXT = "fold(name || ' ' || full_name || ' ' || model || ' ' || tags || ' ' || notes)"


# --- Suche ----------------------------------------------------------------------


def search(conn: sqlite3.Connection, q: str, limit: int = 50) -> list[dict[str, Any]]:
    """Items, deren Name/Tags/Notizen alle Suchwörter (Teilwörter) enthalten, mit Fundort-Pfad.

    Wörter ab 3 Zeichen laufen über FTS5-trigram (Ranking), kürzere über LIKE.
    """
    terms = [t for t in q.replace('"', " ").split() if t]
    if not terms:
        return []
    if all(len(t) >= 3 for t in terms):
        rows = conn.execute(
            "SELECT item.* FROM item_fts JOIN item ON item.id = item_fts.rowid"
            " WHERE item_fts MATCH ? AND item.archived = 0"
            " ORDER BY bm25(item_fts, 10.0, 6.0, 8.0, 5.0, 1.0) LIMIT ?",
            (" AND ".join(f'"{t}"' for t in terms), limit),
        ).fetchall()
    else:
        where = " AND ".join([f"{SEARCH_TEXT} LIKE ?"] * len(terms))
        rows = conn.execute(
            f"SELECT * FROM item WHERE {where} AND archived = 0 ORDER BY name LIMIT ?",
            (*(f"%{t.casefold()}%" for t in terms), limit),
        ).fetchall()
    return [{**dict(r), "path": path_label(conn, r["container_id"])} for r in rows]


def search_containers(conn: sqlite3.Connection, q: str, limit: int = 20) -> list[dict[str, Any]]:
    """Behälter nach Name/Notizen (Fächer nur mit eigenem Namen) oder exaktem Code."""
    terms = q.split()
    if not terms:
        return []
    where = " AND ".join(["fold(name || ' ' || notes) LIKE ?"] * len(terms))
    rows = conn.execute(
        f"SELECT * FROM container WHERE (code = ? OR ({where}))"
        " AND NOT (kind = 'compartment' AND name = 'Fach ' || position) ORDER BY name LIMIT ?",
        (q.strip(), *(f"%{t.casefold()}%" for t in terms), limit),
    ).fetchall()
    return [{**dict(r), "path": path_label(conn, r["id"])} for r in rows]


def parse_synonyms(text: str) -> dict[str, list[str]]:
    """Zeilen wie 'inbus = innensechskant = allen' -> jedes Wort -> ganze Gruppe."""
    groups: dict[str, list[str]] = {}
    for line in text.splitlines():
        words = [w.strip().casefold() for w in line.replace(",", "=").split("=") if w.strip()]
        if len(words) > 1:
            for w in words:
                groups[w] = words
    return groups


def search_synonyms(
    conn: sqlite3.Connection, q: str, synonyms: dict[str, list[str]], limit: int = 50
) -> list[dict[str, Any]]:
    """Wie search(), aber jedes Wort darf auch durch ein Synonym erfüllt sein."""
    terms = [t.casefold() for t in q.replace('"', " ").split() if t]
    if not terms:
        return []
    groups = [synonyms.get(t, [t]) if t in synonyms else [t] for t in terms]
    if all(len(w) >= 3 for g in groups for w in g):
        match = " AND ".join("(" + " OR ".join(f'"{w}"' for w in g) + ")" for g in groups)
        rows = conn.execute(
            "SELECT item.* FROM item_fts JOIN item ON item.id = item_fts.rowid"
            " WHERE item_fts MATCH ? AND item.archived = 0"
            " ORDER BY bm25(item_fts, 10.0, 6.0, 8.0, 5.0, 1.0) LIMIT ?",
            (match, limit),
        ).fetchall()
    else:
        text = SEARCH_TEXT
        where = " AND ".join("(" + " OR ".join([f"{text} LIKE ?"] * len(g)) + ")" for g in groups)
        rows = conn.execute(
            f"SELECT * FROM item WHERE {where} AND archived = 0 ORDER BY name LIMIT ?",
            (*(f"%{w}%" for g in groups for w in g), limit),
        ).fetchall()
    return [{**dict(r), "path": path_label(conn, r["container_id"])} for r in rows]


def suggest(conn: sqlite3.Connection, q: str) -> str | None:
    """Tippfehler-Korrektur: ähnlichstes vorhandenes Wort je Suchwort (oder None)."""
    import difflib
    import re

    vocab: set[str] = set()
    for row in conn.execute("SELECT name, tags FROM item"):
        vocab.update(w.casefold() for w in re.findall(r"\w{3,}", f"{row['name']} {row['tags']}"))
    fixed, changed = [], False
    for term in q.casefold().split():
        if term in vocab or len(term) < 3:
            fixed.append(term)
            continue
        match = difflib.get_close_matches(term, vocab, n=1, cutoff=0.75)
        fixed.append(match[0] if match else term)
        changed |= bool(match)
    return " ".join(fixed) if changed else None


# --- Alltag: Rückgängig, Verleihen, Einkauf, Platz, Favoriten -----------------------

UNDOABLE = ("take", "put", "move", "add")


def undo(conn: sqlite3.Connection, event_id: int) -> str:
    """Macht Entnahme/Einlagern/Umlagern/Hinzufügen rückgängig; gibt eine Meldung zurück."""
    ev = conn.execute("SELECT * FROM event WHERE id = ?", (event_id,)).fetchone()
    if ev is None or ev["undone"] or ev["action"] not in UNDOABLE:
        raise LagerError("Das lässt sich nicht (mehr) rückgängig machen")
    name = ev["item_name"]
    if ev["action"] in ("take", "put"):
        if ev["item_id"] is None:
            raise LagerError("Teil existiert nicht mehr")
        if ev["delta"]:
            change_qty(conn, ev["item_id"], -ev["delta"], note="rückgängig")
        msg = f"Mengenänderung bei „{name}“ zurückgenommen"
    elif ev["action"] == "move":
        if ev["prev_container_id"] is None:
            raise LagerError("Alter Ort unbekannt")
        if ev["item_id"] is not None:
            move_item(conn, ev["item_id"], ev["prev_container_id"])
        elif ev["container_id"] is not None:
            move_container(conn, ev["container_id"], ev["prev_container_id"] or None)
        else:
            raise LagerError("Objekt existiert nicht mehr")
        msg = f"„{name}“ zurück an alten Ort"
    else:  # add
        if ev["item_id"] is None:
            raise LagerError("Teil existiert nicht mehr")
        delete_item(conn, ev["item_id"])
        msg = f"„{name}“ wieder entfernt"
    with conn:
        conn.execute("UPDATE event SET undone = 1 WHERE id = ?", (event_id,))
    return msg


def undo_last(conn: sqlite3.Connection) -> str:
    """Letzte rückgängig-fähige Aktion zurücknehmen."""
    ev = conn.execute(
        "SELECT id FROM event WHERE undone = 0 AND action IN ('take','put','move','add')"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if ev is None:
        raise LagerError("Nichts zum Rückgängigmachen")
    return undo(conn, ev["id"])


def redo_last(conn: sqlite3.Connection) -> str:
    """Zuletzt zurückgenommene Aktion wiederholen (Hinzufügen lässt sich nicht wiederholen)."""
    ev = conn.execute(
        "SELECT * FROM event WHERE undone = 1 AND action IN ('take','put','move')"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if ev is None:
        raise LagerError("Nichts zum Wiederholen")
    if ev["action"] == "move":
        if ev["container_id"] is None:
            raise LagerError("Ziel existiert nicht mehr")
        if ev["item_id"] is not None:
            move_item(conn, ev["item_id"], ev["container_id"])
        else:
            raise LagerError("Nur Teile lassen sich wiederholen")
    elif ev["item_id"] is None:
        raise LagerError("Teil existiert nicht mehr")
    elif ev["delta"]:
        change_qty(conn, ev["item_id"], ev["delta"], note="wiederholt")
    with conn:
        conn.execute("UPDATE event SET undone = 0 WHERE id = ?", (ev["id"],))
    return f"„{ev['item_name']}“ erneut ausgeführt"


def recent_events(conn: sqlite3.Connection, limit: int = 50) -> list[Row]:
    return conn.execute(
        "SELECT e.*, c.name AS container_name FROM event e"
        " LEFT JOIN container c ON c.id = e.container_id ORDER BY e.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def lend_item(conn: sqlite3.Connection, item_id: int, to: str) -> None:
    item = get_item(conn, item_id)
    to = to.strip() or "unbekannt"
    with conn:
        conn.execute(
            "UPDATE item SET lent_to = ?, lent_since = date('now'), updated_at = datetime('now')"
            " WHERE id = ?",
            (to, item_id),
        )
        _log(conn, item, "lend", note=to)


def return_item(conn: sqlite3.Connection, item_id: int) -> None:
    item = get_item(conn, item_id)
    with conn:
        conn.execute(
            "UPDATE item SET lent_to = NULL, lent_since = NULL, updated_at = datetime('now')"
            " WHERE id = ?",
            (item_id,),
        )
        _log(conn, item, "return", note=item["lent_to"] or "")


def _with_path(conn: sqlite3.Connection, rows: list[Row]) -> list[dict[str, Any]]:
    return [{**dict(r), "path": path_label(conn, r["container_id"])} for r in rows]


def lent_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM item WHERE lent_to IS NOT NULL ORDER BY lent_since, name"
    ).fetchall()
    return _with_path(conn, rows)


def shopping_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Manuell markierte Teile und alles unter Mindestbestand.

    Mindestbestand: Wert am Teil, sonst Standard des Typs (`type_setting.min_qty`).
    """
    rows = conn.execute(
        "SELECT i.*, COALESCE(i.min_qty, ts.min_qty) AS min_eff,"
        " (i.min_qty IS NULL AND ts.min_qty IS NOT NULL) AS min_from_type"
        " FROM item i"
        " LEFT JOIN type_setting ts ON ts.key = COALESCE(i.ctype, 'mat:' || i.material)"
        " WHERE (i.on_list = 1 OR (COALESCE(i.min_qty, ts.min_qty) IS NOT NULL"
        " AND i.qty IS NOT NULL AND i.qty < COALESCE(i.min_qty, ts.min_qty))) AND i.archived = 0"
        " ORDER BY i.ordered_at IS NOT NULL, i.name"
    ).fetchall()
    out = _with_path(conn, rows)
    for r in out:
        qty, low = r["qty"], r["min_eff"]
        # Bedarf: Wunschmenge, sonst bis zum Mindestbestand auffüllen, sonst 1
        need = r["order_qty"] or (
            low - qty if low is not None and qty is not None and low > qty else 1
        )
        r["need"] = int(need)
        r["cost"] = float(r["price"]) * r["need"] if r["price"] is not None else None
    return out


def free_places(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Leere Boxen/Kisten und Sortierkästen mit freien Fächern."""
    empty = conn.execute(
        "SELECT c.* FROM container c WHERE c.kind IN"
        " ('toolbox', 'case', 'module', 'eurobox', 'crate', 'box', 'drawer')"
        " AND NOT EXISTS (SELECT 1 FROM item i WHERE i.container_id = c.id)"
        " AND NOT EXISTS (SELECT 1 FROM container k WHERE k.parent_id = c.id) ORDER BY c.name"
    ).fetchall()
    kaesten = conn.execute(
        """
        SELECT k.*, COUNT(f.id) AS total,
               SUM(NOT EXISTS (SELECT 1 FROM item i WHERE i.container_id = f.id)) AS free,
               GROUP_CONCAT(CASE WHEN NOT EXISTS (SELECT 1 FROM item i WHERE i.container_id = f.id)
                            THEN f.position END, ' ') AS free_slots
        FROM container k JOIN container f ON f.parent_id = k.id AND f.kind = 'compartment'
        WHERE k.kind = 'sortingbox' GROUP BY k.id HAVING free > 0 ORDER BY k.name
        """
    ).fetchall()
    return {
        "empty": [{**dict(r), "path": path_label(conn, r["id"])} for r in empty],
        "kaesten": [{**dict(r), "path": path_label(conn, r["id"])} for r in kaesten],
    }


def set_favorite(conn: sqlite3.Connection, container_id: int, on: bool) -> None:
    with conn:
        conn.execute("UPDATE container SET favorite = ? WHERE id = ?", (int(on), container_id))


def containers_by_ids(conn: sqlite3.Connection, ids: list[int]) -> list[Row]:
    """In der Reihenfolge der IDs (für 'Zuletzt angesehen')."""
    if not ids:
        return []
    rows = {
        r["id"]: r
        for r in conn.execute(
            f"SELECT * FROM container WHERE id IN ({','.join('?' * len(ids))})", ids
        )
    }
    return [rows[i] for i in ids if i in rows]


def favorites(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute("SELECT * FROM container WHERE favorite = 1 ORDER BY name").fetchall()


# --- Eingang „Zu sortieren“ ----------------------------------------------------------

INBOX_NAME = "Zu sortieren"


def inbox(conn: sqlite3.Connection) -> int:
    """Eingangs-Behälter für Teile ohne Ort (Sprach-Erfassung); wird bei Bedarf angelegt."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'inbox_id'").fetchone()
    if row and get_container(conn, int(row["value"])) is not None:
        return int(row["value"])
    cid = create_container(conn, INBOX_NAME, "box", notes="Eingang: Teile ohne festen Ort")
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('inbox_id', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(cid),),
        )
    return cid
