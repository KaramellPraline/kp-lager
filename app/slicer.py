"""Slicer-Anbindung (Creality Print / Orca / Cura): Verbrauch aus G-Code oder 3MF lesen, buchen.

Creality Print schreibt am Ende der G-Code-Datei Kommentare wie
  ; filament used [g] = 12.34, 3.2   ; filament_type = PLA;PETG
  ; filament_colour = #FFFFFF;#000000
  ; estimated printing time (normal mode) = 1h 2m 3s
(ältere Cura-Versionen: ';Filament used: 1.23m' und ';TIME:3723'). 3MF-Projekte enthalten
Metadata/slice_info.config mit <filament used_g=…>. Es werden nur Anfang und Ende gelesen.
"""

import io
import json
import math
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app import materials
from app.repo import LagerError

CHUNK = 300_000
MAX_BYTES = 400_000_000
GCODE_SUFFIXES = (".gcode", ".gco", ".3mf", ".gcode.3mf")


@dataclass
class Filament:
    grams: float
    type: str = ""
    color: str = ""
    meters: float = 0.0


@dataclass
class Job:
    name: str
    seconds: int | None = None
    filaments: list[Filament] = field(default_factory=list)


def _floats(raw: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", raw)]


def _seconds(raw: str) -> int | None:
    parts = re.findall(r"(\d+)\s*([dhms])", raw)
    if not parts:
        return None
    mult = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * mult[u] for n, u in parts)


def _grams_from_meters(meters: float, density: float = 1.24, diameter: float = 1.75) -> float:
    return meters * 100 * math.pi * (diameter / 20) ** 2 * density  # cm × cm² × g/cm³


def parse_gcode(text: str, name: str) -> Job:
    def find(pattern: str) -> str | None:
        found = re.findall(pattern, text, flags=re.M | re.I)
        return found[-1].strip() if found else None

    job = Job(name=name)
    grams = find(r"^;\s*filament used \[g\]\s*=\s*(.+)$")
    if grams is None:
        grams = find(r"^;\s*total filament used \[g\]\s*=\s*(.+)$")
    meters_mm = find(r"^;\s*filament used \[mm\]\s*=\s*(.+)$")
    types = (find(r"^;\s*filament_type\s*=\s*(.+)$") or "").split(";")
    colors = (find(r"^;\s*filament_colou?r\s*=\s*(.+)$") or "").split(";")
    g_list = _floats(grams) if grams else []
    m_list = [x / 1000 for x in _floats(meters_mm)] if meters_mm else []
    if not g_list:
        cura = find(r"^;\s*Filament used:\s*([\d.]+)\s*m")
        if cura:
            m_list = [float(cura)]
            g_list = [round(_grams_from_meters(m_list[0]), 1)]
    for i, g in enumerate(g_list):
        if g <= 0:
            continue
        job.filaments.append(
            Filament(
                grams=g,
                type=types[i].strip().strip('"') if i < len(types) else "",
                color=colors[i].strip().strip('"') if i < len(colors) else "",
                meters=m_list[i] if i < len(m_list) else 0.0,
            )
        )
    t = find(r"^;\s*estimated printing time[^=]*=\s*(.+)$") or find(r"^;\s*TIME:\s*(\d+)")
    if t:
        job.seconds = int(t) if t.isdigit() else _seconds(t)
    return job


def parse_3mf(data: bytes, name: str) -> Job:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        info = next((n for n in names if n.endswith("slice_info.config")), None)
        job = Job(name=name)
        if info:
            xml = z.read(info).decode("utf-8", "replace")
            for tag in re.findall(r"<filament\b[^>]*>", xml):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
                grams = float(attrs.get("used_g") or 0)
                if grams > 0:
                    job.filaments.append(
                        Filament(grams, attrs.get("type", ""), attrs.get("color", ""),
                                 float(attrs.get("used_m") or 0))
                    )  # fmt: skip
            if m := re.search(r'key="prediction"\s+value="(\d+)"', xml):
                job.seconds = int(m.group(1))
        if not job.filaments:  # Fallback: G-Code im Projekt
            gc = next((n for n in names if n.endswith(".gcode")), None)
            if gc:
                raw = z.read(gc)
                return parse_gcode(
                    (raw[:CHUNK] + b"\n" + raw[-CHUNK:]).decode("utf-8", "replace"), name
                )
        return job


def parse_bytes(data: bytes, filename: str) -> Job:
    """G-Code oder 3MF (ggf. .gcode.3mf) -> Job."""
    name = re.sub(r"(\.gcode)?\.(3mf|gcode|gco)$", "", Path(filename).name, flags=re.I)
    if len(data) > MAX_BYTES:
        raise LagerError("Datei zu groß")
    if data[:2] == b"PK":
        return parse_3mf(data, name)
    head, tail = data[:CHUNK], data[-CHUNK:] if len(data) > CHUNK else b""
    job = parse_gcode((head + b"\n" + tail).decode("utf-8", "replace"), name)
    if not job.filaments:
        raise LagerError("Keinen Filamentverbrauch gefunden – ist das ein exportierter G-Code?")
    return job


def parse_file(path: Path) -> Job:
    if path.stat().st_size > MAX_BYTES:
        raise LagerError("Datei zu groß")
    with path.open("rb") as f:
        if f.read(2) == b"PK":
            return parse_3mf(path.read_bytes(), path.name)
        f.seek(0)
        head = f.read(CHUNK)
        f.seek(max(0, path.stat().st_size - CHUNK))
        tail = f.read()
    job = parse_gcode((head + b"\n" + tail).decode("utf-8", "replace"), path.stem)
    if not job.filaments:
        raise LagerError("Keinen Filamentverbrauch gefunden")
    return job


def save_job(conn: sqlite3.Connection, job: Job, source: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO print_job (name, source, grams, seconds) VALUES (?,?,?,?)",
            (job.name, source,
             json.dumps([f.__dict__ for f in job.filaments], ensure_ascii=False), job.seconds),
        )  # fmt: skip
    return int(cur.lastrowid or 0)


def spools(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Alle Filament-Spulen mit Restmenge (für die Auswahl beim Buchen)."""
    out = []
    for r in conn.execute(
        "SELECT * FROM item WHERE material = 'fil' AND archived = 0 ORDER BY name"
    ):
        s = materials.specs(r)
        info = materials.remaining(r)
        out.append({
            "id": r["id"], "name": r["name"], "code": r["code"] or "",
            "material": s.get("material", ""), "color": s.get("color", ""),
            "rest": info["text"] if info else "",
        })  # fmt: skip
    return out


def suggest(job: Job, all_spools: list[dict[str, Any]]) -> list[int | None]:
    """Je Filament die Spule mit passendem Material (zuerst die mit bekanntem Rest)."""
    used: set[int] = set()
    out: list[int | None] = []
    for f in job.filaments:
        pick = None
        for s in all_spools:
            if s["id"] in used:
                continue
            if f.type and str(s["material"]).casefold() == f.type.casefold():
                pick = int(str(s["id"]))
                break
        if pick is not None:
            used.add(pick)
        out.append(pick)
    return out


def book(conn: sqlite3.Connection, job_id: int, spool_ids: list[int | None]) -> str:
    """Verbrauch von der Restmenge der gewählten Spulen abziehen; Job als gebucht markieren."""
    job = conn.execute("SELECT * FROM print_job WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise LagerError("Auftrag nicht gefunden")
    if job["booked_at"]:
        raise LagerError("Dieser Druck ist schon gebucht")
    filaments = json.loads(job["grams"])
    done = []
    for f, spool_id in zip(filaments, spool_ids, strict=False):
        if not spool_id:
            continue
        item = conn.execute(
            "SELECT * FROM item WHERE id = ? AND material = 'fil'", (spool_id,)
        ).fetchone()
        if item is None:
            continue
        s = materials.specs(item)
        rest = materials._num(s.get("rest_g", ""))
        if rest is None:
            rest = materials._num(s.get("weight", "")) or 0.0  # unbenutzt: Nettogewicht
        rest = max(0.0, rest - float(f["grams"]))
        s["rest_g"] = f"{rest:.0f}"
        s["rest_date"] = date.today().isoformat()
        with conn:
            conn.execute(
                "UPDATE item SET specs = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(s, ensure_ascii=False), item["id"]),
            )
        info = materials.remaining(
            conn.execute("SELECT * FROM item WHERE id = ?", (item["id"],)).fetchone()
        )
        if info and info["low"]:
            with conn:
                conn.execute("UPDATE item SET on_list = 1 WHERE id = ?", (item["id"],))
        done.append(f"{item['name']} −{float(f['grams']):.0f} g")
        f["item_id"] = item["id"]
    with conn:
        conn.execute(
            "UPDATE print_job SET booked_at = datetime('now', 'localtime'), grams = ? WHERE id = ?",
            (json.dumps(filaments, ensure_ascii=False), job_id),
        )
    return "Gebucht: " + (", ".join(done) if done else "keine Spule gewählt")


def _duration(seconds: int | None) -> str:
    return f"{seconds // 3600} h {seconds % 3600 // 60} min" if seconds else ""


def jobs(conn: sqlite3.Connection, limit: int = 30) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM print_job ORDER BY id DESC LIMIT ?", (limit,)):
        fil = json.loads(r["grams"])
        out.append({
            **dict(r), "filaments": fil, "total_g": sum(float(f["grams"]) for f in fil),
            "time": _duration(r["seconds"]),
        })  # fmt: skip
    return out


def scan_folder(conn: sqlite3.Connection, folder: str, limit: int = 20) -> tuple[int, list[str]]:
    """Neue G-Code/3MF-Dateien eines Ordners einlesen (bekannte Dateinamen werden übersprungen)."""
    path = Path(folder).expanduser()
    if not folder or not path.is_dir():
        raise LagerError("Slicer-Ordner ist nicht eingestellt oder existiert nicht")
    known = {r["source"] for r in conn.execute("SELECT source FROM print_job")}
    files = sorted(
        (p for p in path.iterdir() if p.is_file() and p.name.lower().endswith(GCODE_SUFFIXES)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    added, errors = 0, []
    for p in files:
        if p.name in known:
            continue
        try:
            save_job(conn, parse_file(p), p.name)
            added += 1
        except (LagerError, OSError, zipfile.BadZipFile) as exc:
            errors.append(f"{p.name}: {exc}")
    return added, errors
