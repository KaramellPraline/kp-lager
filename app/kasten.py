"""Sortierkasten-Modelle mit Einsätzen (Bins): Belegung, Platzprüfung, Draufsicht-Daten.

Zellen: Zeile als Buchstabe, Spalte als Zahl (A1 oben links).
Einsatz-Größe 'BxT' = Spalten x Zeilen.
"""

import sqlite3
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Any

from app import codes, repo
from app.repo import LagerError, Row

CELL = 100  # SVG-Einheiten je Rasterzelle


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    cols: int
    rows: int
    blocked: frozenset[str]
    blocked_label: str = "Griff"


MODELS = {
    "norb16": Model("norb16", "Kistenberg NORB16", cols=5, rows=7,
                    blocked=frozenset({"C1", "D1", "E1"})),
}  # fmt: skip
SIZES = ("1x1", "2x1", "1x2", "2x2", "3x1", "4x1")
DIVS = ("1x1", "2x1", "3x1", "4x1", "5x1", "1x2", "2x2", "3x2")


def parse_cell(pos: str) -> tuple[int, int]:
    pos = pos.strip().upper()
    if len(pos) < 2 or pos[0] not in ascii_uppercase or not pos[1:].isdigit():
        raise LagerError(f"Zelle '{pos}' ungültig, z. B. B3")
    return ascii_uppercase.index(pos[0]), int(pos[1:]) - 1


def cell_name(row: int, col: int) -> str:
    return f"{ascii_uppercase[row]}{col + 1}"


def parse_size(size: str) -> tuple[int, int]:
    try:
        w, d = (int(p) for p in size.lower().split("x"))
    except ValueError:
        raise LagerError(f"Größe '{size}' ungültig, z. B. 2x1") from None
    if w < 1 or d < 1:
        raise LagerError("Größe mindestens 1x1")
    return w, d


def cells_of(pos: str, size: str) -> set[str]:
    row, col = parse_cell(pos)
    w, d = parse_size(size)
    return {cell_name(row + r, col + c) for r in range(d) for c in range(w)}


def model_of(kasten: Row) -> Model | None:
    return MODELS.get(kasten["model"] or "")


def bins(conn: sqlite3.Connection, kasten_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM container WHERE parent_id = ? AND kind = 'einsatz' ORDER BY position",
        (kasten_id,),
    ).fetchall()


def occupied(conn: sqlite3.Connection, kasten_id: int) -> dict[str, int]:
    return {c: b["id"] for b in bins(conn, kasten_id) for c in cells_of(b["position"], b["size"])}


def check_place(model: Model, taken: dict[str, int], pos: str, size: str) -> None:
    row, col = parse_cell(pos)
    w, d = parse_size(size)
    if row + d > model.rows or col + w > model.cols:
        raise LagerError(f"{size} passt ab {pos} nicht mehr in den Kasten")
    cells = cells_of(pos, size)
    if blocked := cells & model.blocked:
        raise LagerError(f"Zelle {', '.join(sorted(blocked))} ist der {model.blocked_label}")
    if clash := cells & taken.keys():
        raise LagerError(f"Zelle {', '.join(sorted(clash))} ist schon belegt")


def place_bin(
    conn: sqlite3.Connection, kasten_id: int, pos: str, size: str, div: str = "1x1"
) -> int:
    kasten = repo.get_container(conn, kasten_id)
    model = model_of(kasten) if kasten else None
    if kasten is None or model is None:
        raise LagerError("Kein Sortierkasten mit Modell")
    pos = pos.strip().upper()
    check_place(model, occupied(conn, kasten_id), pos, size)
    w, d = parse_size(size)
    code = codes.reserve(conn, "EIN", 1)[0]
    return repo.create_container(
        conn,
        f"Einsatz {pos}",
        "einsatz",
        parent_id=kasten_id,
        code=code,
        position=pos,
        grid=div if div and div != "1x1" else None,
        size=f"{w}x{d}",
    )


def free_cells(conn: sqlite3.Connection, kasten: Row) -> list[str]:
    model = model_of(kasten)
    if model is None:
        return []
    taken = occupied(conn, kasten["id"])
    return [
        cell_name(r, c)
        for r in range(model.rows)
        for c in range(model.cols)
        if cell_name(r, c) not in taken and cell_name(r, c) not in model.blocked
    ]


def bin_items(conn: sqlite3.Connection, bin_id: int) -> list[Row]:
    """Teile im Einsatz inkl. Fächern, in Fach-Reihenfolge."""
    return conn.execute(
        "SELECT i.*, c.position AS slot FROM item i JOIN container c ON c.id = i.container_id"
        " WHERE c.id = ? OR c.parent_id = ? ORDER BY c.id, i.name",
        (bin_id, bin_id),
    ).fetchall()


def bin_label_text(conn: sqlite3.Connection, bin_row: Row) -> str:
    names = [i["name"] for i in bin_items(conn, bin_row["id"])]
    return ", ".join(dict.fromkeys(names)) or bin_row["name"]


def cad_command(bin_row: Row) -> str:
    div = bin_row["grid"] or "1x1"
    return f"uv run --group cad python cad/norb_bins.py {bin_row['size']} --div {div}"


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def topview(conn: sqlite3.Connection, kasten: Row) -> dict[str, Any] | None:
    """Zeichendaten für die SVG-Draufsicht (Koordinaten in CELL-Einheiten)."""
    model = model_of(kasten)
    if model is None:
        return None
    drawn_bins = []
    for b in bins(conn, kasten["id"]):
        row, col = parse_cell(b["position"])
        w, d = parse_size(b["size"])
        x, y, bw, bh = col * CELL, row * CELL, w * CELL, d * CELL
        comps = []
        faecher = repo.children(conn, b["id"])
        if faecher and b["grid"]:
            fc, fr = (int(p) for p in b["grid"].split("x"))
            for f in faecher:
                frow, fcol = parse_cell(f["position"])
                cw, chh = bw / fc, bh / fr
                names = f["item_names"].split(", ") if f["item_names"] else []
                comps.append(
                    {"id": f["id"], "x": x + fcol * cw, "y": y + frow * chh, "w": cw, "h": chh,
                     "names": names}
                )  # fmt: skip
        else:
            items = [i["name"] for i in repo.items_in(conn, b["id"])]
            comps.append({"id": b["id"], "x": x, "y": y, "w": bw, "h": bh, "names": items})
        for c in comps:
            per_line = max(4, int(c["w"] / 9))
            c["lines"] = [_short(n, per_line) for n in c["names"][: max(1, int(c["h"] / 22) - 1)]]
        drawn_bins.append(
            {"id": b["id"], "code": b["code"], "pos": b["position"], "size": b["size"],
             "x": x, "y": y, "w": bw, "h": bh, "comps": comps}
        )  # fmt: skip
    blocked = sorted(model.blocked)
    rows = [parse_cell(c) for c in blocked]
    return {
        "model": model,
        "width": model.cols * CELL,
        "height": model.rows * CELL,
        "bins": drawn_bins,
        "free": [
            {"cell": c, "x": parse_cell(c)[1] * CELL, "y": parse_cell(c)[0] * CELL}
            for c in free_cells(conn, kasten)
        ],
        "blocked": [{"x": c * CELL, "y": r * CELL} for r, c in rows],
    }


def quick_targets(conn: sqlite3.Connection, kasten: Row) -> list[dict[str, Any]]:
    """Auswahl für die Schnelleingabe: jedes Fach bzw. jeder Einsatz ohne Fächer."""
    out = []
    for b in bins(conn, kasten["id"]):
        faecher = repo.children(conn, b["id"])
        if faecher:
            for f in faecher:
                out.append({"id": f["id"], "label": f"{b['position']} · Fach {f['position']}"
                            + (f" – {f['item_names']}" if f["item_names"] else "")})  # fmt: skip
        else:
            names = ", ".join(i["name"] for i in repo.items_in(conn, b["id"]))
            out.append({"id": b["id"], "label": f"{b['position']} ({b['size']})"
                        + (f" – {names}" if names else "")})  # fmt: skip
    return out


def bin_of(conn: sqlite3.Connection, container_id: int) -> Row | None:
    """Einsatz, zu dem ein Fach/Einsatz gehört (für das Bin-Etikett)."""
    for node in reversed(repo.container_path(conn, container_id)):
        if node["kind"] == "einsatz":
            return node
    return None
