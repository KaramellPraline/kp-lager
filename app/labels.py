"""Etiketten: QR-Inhalt, Texte, Layout je Typ und Warteschlange für den D30 (40×12 mm).
A4-Etiketten: `app/a4.py`.

QR-Inhalt komplett in Großbuchstaben (HTTP://LAGER.HOME.LAN/C/EUR-001): Dann nutzt der QR den
Alphanumerik-Modus, wird eine Version kleiner und auf 10 mm besser scannbar. /C/ = /c/.
"""

import copy
import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

import segno

from app import codes, repo

TEXT_MAX = 24  # Zeichen, die auf 40×12 mm neben den QR passen


@dataclass(frozen=True)
class Label:
    code: str
    qr: str
    text: str = ""
    extra: str = ""
    # Layout je Typ: ((Text, Höhenanteil, Ausrichtung), …) und QR-Position; leer = Standard
    lines: tuple[tuple[str, int, str], ...] = ()
    qr_pos: str = "left"


# --- Layout je Typ -------------------------------------------------------------------------

QR_POSITIONS = ("left", "right", "none")
ALIGNS = ("left", "center", "right")
MAX_LINES = 4
Layout = dict[str, Any]
DEFAULT_LAYOUT: Layout = {
    "qr": "left",
    "lines": [{"t": "{name}", "w": 1, "a": "center"}, {"t": "{code}", "w": 1, "a": "center"}],
}


# Vorlagen fürs Layout (Designer: Knöpfe; „Alles“ passt für jeden Typ, weil leere Felder wegfallen)
PRESETS: dict[str, tuple[str, Layout]] = {
    "alles": (
        "Alles (Name · Maße · Ort)",
        {
            "qr": "left",
            "lines": [
                {"t": "{name}", "w": 3, "a": "left"},
                {"t": "{thread}x{length} {value} {voltage} {size}", "w": 2, "a": "left"},
                {"t": "{code} {ort}", "w": 1, "a": "left"},
            ],
        },
    ),
    "standard": ("Name + Code", DEFAULT_LAYOUT),
    "gross": (
        "Nur Name, groß",
        {"qr": "none", "lines": [{"t": "{name}", "w": 4, "a": "center"}]},
    ),
}


def default_layout() -> Layout:
    return copy.deepcopy(DEFAULT_LAYOUT)


def parse_layout(raw: str | Layout | None) -> Layout:
    """JSON-Layout prüfen und bereinigen; ungültig/leer -> Standard (Name + Code)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else None
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        return default_layout()
    qr = raw.get("qr") if raw.get("qr") in QR_POSITIONS else "left"
    lines: list[dict[str, Any]] = []
    given = raw.get("lines")
    for ln in given if isinstance(given, list) else []:
        if len(lines) >= MAX_LINES:
            break
        if not isinstance(ln, dict):
            continue
        tpl = str(ln.get("t", "")).strip()[:80]
        if not tpl:
            continue
        try:
            weight = max(1, min(4, int(ln.get("w", 1))))
        except (TypeError, ValueError):
            weight = 1
        align = ln.get("a") if ln.get("a") in ALIGNS else "center"
        lines.append({"t": tpl, "w": weight, "a": align})
    return {"qr": qr, "lines": lines or default_layout()["lines"]}


def layout_lines(layout: Layout, values: dict[str, str]) -> tuple[tuple[str, int, str], ...]:
    """Vorlagen mit Werten füllen; leere Zeilen fallen weg (Höhe verteilt sich neu)."""
    out = []
    for ln in layout["lines"]:
        text = fill(ln["t"], values)
        if text:
            out.append((text, int(ln["w"]), str(ln["a"])))
    return tuple(out)


def qr_content(base_url: str, code: str) -> str:
    return f"{base_url}/C/{code}".upper()


def qr_svg(content: str) -> str:
    """Inline-SVG ohne feste Größe (skaliert per CSS)."""
    svg: str = segno.make(content, error="m").svg_inline(border=0, omitsize=True)
    return svg


def short(text: str, limit: int = TEXT_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- Etikettenlisten ---------------------------------------------------------------


def blank(conn: sqlite3.Connection, base_url: str, prefix: str, count: int) -> list[Label]:
    """Vorrat: die nächsten freien Codes (reserviert erst beim Export)."""
    start = codes.next_number(conn, prefix)
    return [
        Label(c, qr_content(base_url, c), codes.PREFIX_LABELS[prefix])
        for c in (codes.format_code(prefix, n) for n in range(start, start + count))
    ]


# Felder, die bei jedem Teil im Etikett verwendbar sind ({key} in der Zeile)
EXTRA_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "Name"), ("full_name", "Voller Name"), ("code", "Code"), ("ort", "Ort"),
    ("qty", "Menge"), ("unit", "Einheit"), ("model", "Modell"), ("notes", "Notiz"),
    ("tags", "Tags"), ("price", "Preis"), ("expires", "Haltbar bis"),
)  # fmt: skip


def fill(template: str, values: dict[str, str]) -> str:
    """„{thread}x{length} {head}“ -> „M3x10 Zylinderkopfschraube“; leere Felder fallen weg
    (samt direkt angehängter Zeichen wie „x“ oder „mm“, wenn sie dadurch allein stünden)."""
    out = []
    for token in template.split():
        keys = re.findall(r"{(\w+)}", token)
        if keys and not all(values.get(k, "").strip() for k in keys):
            continue
        out.append(re.sub(r"{(\w+)}", lambda m: values.get(m.group(1), "").strip(), token))
    seps = ("x", "×", "·", "-", "/")  # Trenner allein: weg, wenn ein Nachbar fehlt
    while out and out[0] in seps:
        out.pop(0)
    while out and out[-1] in seps:
        out.pop()
    out = [t for i, t in enumerate(out) if not (t in seps and i and out[i - 1] in seps)]
    return " ".join(out).strip()


def item_texts(conn: sqlite3.Connection, item: sqlite3.Row) -> tuple[str, str]:
    """(Text, Zusatz) fürs Teile-Etikett: Vorlage des Typs, sonst Name und Ort."""
    from app import typesettings  # spät: Zyklen vermeiden

    values = item_values(conn, item)
    text, extra = item["name"], values["ort"]
    key = typesettings.key_of(item)
    if key:
        ts = typesettings.get(conn, key)
        if ts["label_main"] or ts["label_extra"]:
            text = fill(ts["label_main"], values) or item["name"] if ts["label_main"] else text
            extra = fill(ts["label_extra"], values) if ts["label_extra"] else extra
    return text, extra


def item_values(conn: sqlite3.Connection, item: sqlite3.Row) -> dict[str, str]:
    """Felder fürs Etikett: Typ-Felder, Datenblatt, dazu {name}, {code}, {ort}."""
    from app import catalog, materials

    holder = conn.execute(
        "SELECT kind, name, position FROM container WHERE id = ?", (item["container_id"],)
    ).fetchone()
    place = (holder["position"] if holder["kind"] == "compartment" else holder["name"]) or ""
    values = {**materials.specs(item), **catalog.values_of(item)}
    values.update({"name": item["name"], "code": item["code"] or "", "ort": place})
    for key, _label in EXTRA_FIELDS:  # allgemeine Teile-Felder (überschreiben Typ-Felder nicht)
        if key in ("name", "code", "ort"):
            continue
        raw = item[key] if key in item.keys() else None  # noqa: SIM118 (sqlite3.Row)
        if key == "qty":
            raw = item["qty"] if item["qty"] is not None else item["qty_hint"]
        values.setdefault(
            key, "" if raw is None else f"{raw:g}" if isinstance(raw, float) else str(raw)
        )
    return values


def default_for(conn: sqlite3.Connection, key: str) -> Layout | None:
    """Standard-Layout des Katalog-/eigenen Typs: dreizeilig (Typ+Spec · Maße · Code)."""
    from app import catalog

    t = catalog.lookup(conn, key) if key and not key.startswith("mat:") else None
    return parse_layout(catalog.default_label_layout(t)) if t else None


def type_layout(conn: sqlite3.Connection, item: sqlite3.Row) -> Layout | None:
    """Layout des Typs dieses Teils: gespeichert, sonst dreizeilig; None = Name + Code."""
    from app import typesettings

    key = typesettings.key_of(item)
    ts = typesettings.get(conn, key) if key else {}
    if ts.get("label_layout"):
        return parse_layout(ts["label_layout"])
    if ts.get("label_main") or ts.get("label_extra"):  # eigene Haupt-/Zusatzzeile hat Vorrang
        return None
    return default_for(conn, key)


def item_label(conn: sqlite3.Connection, base_url: str, item: sqlite3.Row) -> Label:
    text, extra = item_texts(conn, item)
    label = Label(item["code"], qr_content(base_url, item["code"]), text, extra)
    return with_layout(conn, label, item)


def with_layout(conn: sqlite3.Connection, label: Label, item: sqlite3.Row | None = None) -> Label:
    """Layout des Typs anhängen (aus der Warteschlange kommen Etiketten ohne Layout)."""
    if item is None:
        item = conn.execute("SELECT * FROM item WHERE code = ?", (label.code,)).fetchone()
    layout = type_layout(conn, item) if item is not None else None
    if layout is None:
        return label
    lines = layout_lines(layout, item_values(conn, item))
    shown = [t for t, _, _ in lines if t != (item["code"] or "")]  # ohne die reine Code-Zeile
    text = shown[0] if shown else label.text
    extra = shown[1] if len(shown) > 1 else ""
    return Label(label.code, label.qr, text, extra, lines, str(layout["qr"]))


def unprinted_in(conn: sqlite3.Connection, base_url: str, container_id: int) -> list[Label]:
    """Sammeldruck: alle noch nicht gedruckten Etiketten im Behälter samt Unterbehältern
    (Behälter selbst, Unterbehälter mit Code, Teile mit Code)."""
    tree = conn.execute(
        """
        WITH RECURSIVE down(id) AS (
            SELECT id FROM container WHERE id = ?
            UNION ALL SELECT c.id FROM container c JOIN down ON c.parent_id = down.id
        ) SELECT id FROM down
        """,
        (container_id,),
    ).fetchall()
    ids = [r["id"] for r in tree]
    marks = ",".join("?" * len(ids))
    out = []
    for c in conn.execute(
        f"SELECT * FROM container WHERE id IN ({marks}) AND code IS NOT NULL AND label_printed = 0"
        " ORDER BY id",
        ids,
    ):
        text, extra = container_label(conn, c)
        out.append(Label(c["code"], qr_content(base_url, c["code"]), text, extra))
    out += [
        item_label(conn, base_url, i)
        for i in conn.execute(
            f"SELECT * FROM item WHERE container_id IN ({marks}) AND code IS NOT NULL"
            " AND label_printed = 0 AND archived = 0 ORDER BY container_id, name",
            ids,
        )
    ]
    return out


def pending(conn: sqlite3.Connection, base_url: str) -> list[Label]:
    """Alle Behälter und Gegenstände mit Code, deren Etikett noch nicht gedruckt ist."""
    rows = [
        Label(c["code"], qr_content(base_url, c["code"]), c["name"], c["kind"])
        for c in conn.execute(
            "SELECT * FROM container WHERE code IS NOT NULL AND label_printed = 0 ORDER BY code"
        )
    ]
    rows += [
        item_label(conn, base_url, i)
        for i in conn.execute(
            "SELECT * FROM item WHERE code IS NOT NULL AND label_printed = 0 ORDER BY code"
        )
    ]
    return rows


def all_coded(conn: sqlite3.Connection, base_url: str) -> list[Label]:
    """Alle Behälter und Teile mit Code (für die A4-Auswahl), Zusatz = Ort."""
    rows = [
        Label(c["code"], qr_content(base_url, c["code"]), c["name"], c["kind"])
        for c in conn.execute("SELECT * FROM container WHERE code IS NOT NULL ORDER BY code")
    ]
    rows += [
        item_label(conn, base_url, i)
        for i in conn.execute(
            "SELECT * FROM item WHERE code IS NOT NULL AND archived = 0 ORDER BY code"
        )
    ]
    return rows


def for_container(conn: sqlite3.Connection, base_url: str, container_id: int) -> list[Label]:
    """Alle Gegenstände im Behälter inkl. Fächern; fehlende ART-Codes werden vergeben."""
    items = conn.execute(
        """
        WITH RECURSIVE down(id) AS (
            SELECT id FROM container WHERE id = ?
            UNION ALL SELECT c.id FROM container c JOIN down ON c.parent_id = down.id
        )
        SELECT item.id, item.code FROM item JOIN down ON item.container_id = down.id
        JOIN container ON container.id = item.container_id
        ORDER BY container.id, item.name
        """,
        (container_id,),
    ).fetchall()
    missing = [i["id"] for i in items if not i["code"]]
    with conn:
        for item_id, code in zip(
            missing, codes.reserve(conn, codes.ITEM_PREFIX, len(missing)), strict=True
        ):
            conn.execute("UPDATE item SET code = ? WHERE id = ?", (code, item_id))
    return [
        item_label(
            conn, base_url, conn.execute("SELECT * FROM item WHERE id = ?", (i["id"],)).fetchone()
        )
        for i in items
    ]


def finalize(
    conn: sqlite3.Connection,
    base_url: str,
    entries: list[tuple[str, str, str]],
    save_names: bool,
) -> list[Label]:
    """Export aus der Vorschau: (Code, Text, Zusatz) prüfen, ggf. Namen speichern,
    als gedruckt markieren und Zähler je Präfix nachziehen (reserviert Vorrats-Codes)."""
    rows: list[Label] = []
    for raw, text, extra in entries:
        code = codes.normalize(raw)
        if code is None:
            continue
        text = text.strip()
        if save_names and text:
            item = conn.execute("SELECT id, name FROM item WHERE code = ?", (code,)).fetchone()
            if item and item["name"] != text:
                repo.update_item(conn, item["id"], name=text)
            with conn:
                conn.execute(
                    "UPDATE container SET name = ?, updated_at = datetime('now')"
                    " WHERE code = ? AND name != ?",
                    (text, code, text),
                )
        rows.append(Label(code, qr_content(base_url, code), text, extra.strip()))
    printed = [(r.code,) for r in rows]
    with conn:
        conn.executemany("UPDATE container SET label_printed = 1 WHERE code = ?", printed)
        conn.executemany("UPDATE item SET label_printed = 1 WHERE code = ?", printed)
    for prefix in {r.code[:3] for r in rows}:
        last = max(int(r.code[4:]) for r in rows if r.code.startswith(prefix))
        codes.mark_used_until(conn, prefix, last)
    return rows


# --- Warteschlange: Etiketten sammeln, später als Batch exportieren -------------------


def enqueue(conn: sqlite3.Connection, code: str, text: str, extra: str = "") -> None:
    """Gleicher Code nochmal = Text aktualisieren (z. B. Bin-Inhalt geändert)."""
    with conn:
        conn.execute(
            "INSERT INTO label_queue (code, text, extra) VALUES (?, ?, ?) ON CONFLICT(code)"
            " DO UPDATE SET text = excluded.text, extra = excluded.extra",
            (code, text, extra),
        )


def queue(conn: sqlite3.Connection, base_url: str) -> list[Label]:
    return [
        with_layout(conn, Label(r["code"], qr_content(base_url, r["code"]), r["text"], r["extra"]))
        for r in conn.execute("SELECT * FROM label_queue ORDER BY added_at, code")
    ]


def find(conn: sqlite3.Connection, base_url: str, code: str) -> Label | None:
    """Etikett zu einem Code: Warteschlange zuerst, sonst aus dem Bestand."""
    norm = codes.normalize(code)
    for rows in (queue(conn, base_url), all_coded(conn, base_url)):
        for r in rows:
            if r.code == norm:
                return r
    return None


def queue_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM label_queue").fetchone()[0])


def dequeue(conn: sqlite3.Connection, codes_: list[str]) -> None:
    with conn:
        conn.executemany("DELETE FROM label_queue WHERE code = ?", [(c,) for c in codes_])


def container_label(conn: sqlite3.Connection, node: sqlite3.Row) -> tuple[str, str]:
    """(Text, Zusatz) für ein Behälter-Etikett; Einsatz: Inhalt + Kasten/Position."""
    if node["kind"] == "bin":
        parent = repo.get_container(conn, node["parent_id"]) if node["parent_id"] else None
        where = (parent["code"] or parent["name"]) if parent else ""
        # oben auf dem Bin nur der Code-Tag (bleibt gleich); Inhalt kommt aufs Inhaltsetikett
        return f"{where} {node['position']}".strip() or node["name"], ""
    return node["name"], node["kind"]


# --- Inhaltsetiketten (vorne auf Bins und Fächern, nur Text, zum Beschriften) ---------------


def content_text(conn: sqlite3.Connection, node: sqlite3.Row) -> str:
    from app import kasten  # zirkulärer Import vermeiden

    return kasten.bin_label_text(conn, node)


def content_title(conn: sqlite3.Connection, node: sqlite3.Row) -> str:
    """Kennung auf dem Inhaltsetikett: Bin-Code, sonst Kasten-Code + Fach."""
    if node["code"]:
        return str(node["code"])
    parent = repo.get_container(conn, node["parent_id"]) if node["parent_id"] else None
    where = (parent["code"] or parent["name"]) if parent else ""
    return f"{where} {node['position'] or node['name']}".strip()


def enqueue_content(conn: sqlite3.Connection, node: sqlite3.Row) -> None:
    with conn:
        conn.execute(
            "INSERT INTO content_queue (node_id, text) VALUES (?, ?)"
            " ON CONFLICT(node_id) DO UPDATE SET text = excluded.text, added_at = datetime('now')",
            (node["id"], content_text(conn, node)),
        )


def content_queue(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT q.node_id, q.text, c.* FROM content_queue q JOIN container c ON c.id = q.node_id"
        " ORDER BY q.added_at, q.node_id"
    ).fetchall()
    return [{"id": r["node_id"], "title": content_title(conn, r), "text": r["text"]} for r in rows]


def clear_content(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DELETE FROM content_queue")
