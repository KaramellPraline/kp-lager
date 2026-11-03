"""Einkäufe aus Rechnung oder CSV übernehmen (regelbasiert, keine KI).

Eingaben: CSV-Export eines Shops (Kopfzeile wird über Synonyme erkannt, Trennzeichen ; , Tab),
eingefügter Rechnungstext oder PDF-Rechnung (Text wird mit pypdf gelesen). Ergebnis sind Zeilen
mit Name, Menge, Stückpreis, Artikelnummer, die danach Teilen zugeordnet werden.
"""

import csv
import io
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from app import codes, purchases, repo
from app.repo import LagerError

COLUMNS = {
    "name": ("artikel", "bezeichnung", "beschreibung", "produkt", "produktname", "artikelname",
             "name", "item", "description", "title", "titel", "position"),
    "qty": ("menge", "anzahl", "stück", "stueck", "stk", "qty", "quantity", "anz"),
    "price": ("einzelpreis", "stückpreis", "stueckpreis", "preis", "price", "unit price",
              "ep", "e-preis", "netto-einzelpreis", "brutto-einzelpreis"),
    "total": ("gesamt", "gesamtpreis", "summe", "total", "betrag", "gp", "item total"),
    "sku": ("artikelnummer", "art.-nr.", "art.-nr", "artnr", "art-nr", "bestellnummer",
            "best.-nr.", "sku", "asin", "mpn", "artikel-nr.", "artikel-nr"),
    "supplier": ("lieferant", "händler", "haendler", "shop", "seller", "verkäufer", "verkaeufer"),
    "date": ("datum", "bestelldatum", "order date", "rechnungsdatum", "date"),
    "url": ("link", "url", "produktlink"),
}  # fmt: skip
MAX_LINES = 300
PRICE = r"\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,4})|\d+(?:[.,]\d{1,4})?"
SKIP = re.compile(
    r"\b(summe|zwischensumme|gesamt|mwst|ust|versand|porto|rabatt|netto|brutto|total)\b", re.I
)


@dataclass
class Line:
    name: str
    qty: int | None = None
    price: float | None = None  # Stückpreis
    sku: str = ""
    supplier: str = ""
    date: str = ""
    url: str = ""


def money(raw: str) -> float | None:
    """„1.234,56 €“, „12,5“, „3.99“ -> Zahl."""
    raw = re.sub(r"[€$\s]|EUR", "", raw.strip())
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return round(float(raw), 4)
    except ValueError:
        return None


def _qty(raw: str) -> int | None:
    m = re.search(r"\d+(?:[.,]\d+)?", raw or "")
    if not m:
        return None
    value = float(m.group(0).replace(",", "."))
    return max(1, round(value))


def _date(raw: str) -> str:
    raw = raw.strip()
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})", raw):
        return m.group(0)
    if m := re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", raw):
        d, mo, y = m.groups()
        y = y if len(y) == 4 else "20" + y
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


def _header_map(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, col in enumerate(header):
        c = col.strip().casefold().strip('"')
        for key, names in COLUMNS.items():
            if key not in found and (
                c in names or any(c.startswith(n) for n in names if len(n) > 4)
            ):
                found[key] = idx
                break
    return found


def parse_csv(text: str) -> list[Line] | None:
    """CSV mit erkennbarer Kopfzeile (mindestens Name) -> Zeilen; sonst None."""
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        return None
    rows = list(csv.reader(io.StringIO(text), dialect))
    if len(rows) < 2:
        return None
    cols = _header_map(rows[0])
    if "name" not in cols or len(cols) < 2:
        return None
    out = []
    for r in rows[1 : MAX_LINES + 1]:

        def get(key: str, row: list[str] = r) -> str:
            i = cols.get(key)
            return row[i].strip() if i is not None and i < len(row) else ""

        name = get("name")
        if not name:
            continue
        qty = _qty(get("qty")) if get("qty") else None
        price = money(get("price")) if get("price") else None
        total = money(get("total")) if get("total") else None
        if price is None and total is not None:
            price = round(total / (qty or 1), 4)
        out.append(
            Line(name, qty, price, get("sku"), get("supplier"), _date(get("date")), get("url"))
        )
    return out


LINE_RES = (
    # „Pos 1 12345 Lötzinn 0,5mm 2 9,90 19,80“ -> Artikelnummer, Name, Menge, Preis, Summe
    re.compile(rf"^\s*(?:\d+\s+)?(?P<sku>(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{{3,}})\s+(?P<name>.+?)\s+(?P<qty>\d+)\s+(?P<price>{PRICE})\s*(?:€|EUR)?(?:\s+(?P<total>{PRICE})\s*(?:€|EUR)?)?\s*$"),  # noqa: E501
    # „3 x Zylinderkopfschraube M3x10 0,12 € 0,36 €“ / „3 Stk. Widerstand 10k 0,05 0,15“
    re.compile(rf"^\s*(?P<qty>\d+)\s*(?:x|×|stk\.?|st\.?|stück)?\s+(?P<name>.+?)\s+(?P<price>{PRICE})\s*(?:€|EUR)?(?:\s+(?P<total>{PRICE})\s*(?:€|EUR)?)?\s*$", re.I),  # noqa: E501
    # „Lötzinn 0,5mm 2 x 9,90 €“
    re.compile(rf"^\s*(?P<name>.+?)\s+(?P<qty>\d+)\s*(?:x|×|stk\.?|st\.?)\s*(?P<price>{PRICE})\s*(?:€|EUR)?\s*$", re.I),  # noqa: E501
)  # fmt: skip


def parse_text(text: str) -> list[Line]:
    """Rechnungstext (aus PDF oder E-Mail kopiert): typische Positionszeilen erkennen."""
    out = []
    for raw in text.splitlines()[: MAX_LINES * 4]:
        line = re.sub(r"\s{2,}|\t", "  ", raw).strip()
        if not line or SKIP.search(line):
            continue
        for rx in LINE_RES:
            m = rx.match(line)
            if not m:
                continue
            g = m.groupdict()
            name = re.sub(r"\s+", " ", g["name"]).strip(" -–:")
            if len(name) < 2 or not re.search(r"[A-Za-zÄÖÜäöü]", name):
                continue
            qty = int(g["qty"]) if g.get("qty") else None
            price = money(g["price"]) if g.get("price") else None
            total = money(g["total"]) if g.get("total") else None
            if price is None and total is not None:
                price = round(total / (qty or 1), 4)
            out.append(Line(name, qty, price, g.get("sku") or ""))
            break
        if len(out) >= MAX_LINES:
            break
    return out


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:20])
    except Exception as exc:  # beschädigt, verschlüsselt …
        raise LagerError(f"PDF nicht lesbar: {exc}") from None


def parse(text: str = "", data: bytes = b"", filename: str = "") -> list[Line]:
    if data and (filename.lower().endswith(".pdf") or data[:5] == b"%PDF-"):
        text = pdf_text(data)
        return parse_text(text)
    if data:
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    if not text.strip():
        raise LagerError("Keine Daten: CSV/PDF hochladen oder Rechnungstext einfügen")
    lines = parse_csv(text)
    if lines is None:
        lines = parse_text(text)
    if not lines:
        raise LagerError(
            "Keine Positionen erkannt – Spalten Artikel/Menge/Preis oder Zeilen wie „3 x Name 1,20 €“"  # noqa: E501
        )
    return lines


def match(conn: sqlite3.Connection, line: Line, supplier: str = "") -> dict[str, Any]:
    """Zuordnung: gleiche Artikelnummer früher gekauft > gleicher Name > Suchtreffer (Vorschlag)."""
    if line.sku:
        row = conn.execute(
            "SELECT p.item_id FROM purchase p JOIN item i ON i.id = p.item_id"
            " WHERE p.sku = ? AND i.archived = 0 ORDER BY p.id DESC LIMIT 1",
            (line.sku,),
        ).fetchone()
        if row:
            return {"item_id": row["item_id"], "how": "Artikelnummer", "candidates": []}
    row = conn.execute(
        "SELECT id FROM item WHERE fold(name) = fold(?) AND archived = 0 LIMIT 1", (line.name,)
    ).fetchone()
    if row:
        return {"item_id": row["id"], "how": "Name", "candidates": []}
    cands = [
        {"id": c["id"], "name": c["name"], "path": c["path"]}
        for c in repo.search(conn, line.name, limit=5)
    ]
    if not cands:  # wenigstens nach dem ersten Wort suchen
        first = line.name.split()[0] if line.name.split() else ""
        if len(first) >= 3:
            cands = [{"id": c["id"], "name": c["name"], "path": c["path"]}
                     for c in repo.search(conn, first, limit=5)]  # fmt: skip
    return {"item_id": None, "how": "", "candidates": cands}


def preview(conn: sqlite3.Connection, lines: list[Line], supplier: str) -> list[dict[str, Any]]:
    out = []
    for i, ln in enumerate(lines):
        m = match(conn, ln, supplier)
        item = repo.get_item(conn, m["item_id"]) if m["item_id"] else None
        out.append({"idx": i, "line": asdict(ln), "match": m,
                    "item": {"id": item["id"], "name": item["name"]} if item else None})  # fmt: skip  # noqa: E501
    return out


def apply(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    supplier: str,
    bought_at: str = "",
    book: bool = True,
) -> dict[str, int]:
    """rows: [{"line": {...}, "target": "item:<id>" | "new" | "skip"}]."""
    done = {"booked": 0, "created": 0, "skipped": 0}
    inbox = repo.inbox(conn)
    for r in rows:
        ln, target = r["line"], r.get("target", "skip")
        if target == "skip":
            done["skipped"] += 1
            continue
        qty = ln.get("qty")
        if target == "new":
            item_id = repo.add_item(
                conn, inbox, ln["name"], qty=qty, code=codes.new_item_code(conn)
            )
            done["created"] += 1
        elif target.startswith("item:") and target[5:].isdigit():
            item_id = int(target[5:])
            item = repo.get_item(conn, item_id)
            if book and qty:
                if item["qty"] is None:
                    repo.update_item(conn, item_id, qty=qty)
                else:
                    repo.change_qty(conn, item_id, qty, note="Einkauf (Import)")
            if item["ordered_at"] or item["on_list"]:
                repo.update_item(conn, item_id, ordered_at=None, on_list=0)
            done["booked"] += 1
        else:
            done["skipped"] += 1
            continue
        pid = purchases.add(
            conn, item_id, ln.get("supplier") or supplier, qty, ln.get("price"),
            ln.get("date") or bought_at, ln.get("url", ""), "Import",
        )  # fmt: skip
        if ln.get("sku"):
            with conn:
                conn.execute("UPDATE purchase SET sku = ? WHERE id = ?", (ln["sku"], pid))
    return done
