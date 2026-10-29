"""Suche: jedes Wort wird erweitert um eigene Synonyme, Übersetzung DE<->EN (LEXICON) und den
Wortstamm (Schrauben -> Schraube); Wörter ohne Treffer werden automatisch auf das ähnlichste
bekannte Wort korrigiert (Tippfehler). Treffer müssen alle Wörter (bzw. eine Variante) enthalten.
"""

import difflib
import re
import sqlite3
from typing import Any

from app.repo import SEARCH_TEXT, path_label

# Werkstatt-Wortschatz: Gleichbedeutendes je Zeile (Deutsch = Englisch = Varianten)
LEXICON = """schraube = screw = bolt
mutter = nut
unterlegscheibe = scheibe = washer
dübel = anker = anchor = dowel
nagel = nail
niete = rivet
kabel = cable = leitung = wire
draht = wire
litze = strand
stecker = connector = plug
buchse = socket = jack
schalter = switch
taster = button = pushbutton
widerstand = resistor
kondensator = capacitor = elko
diode = led
transistor = mosfet
spule = coil = inductor
sicherung = fuse
relais = relay
akku = battery = accu = batterie
ladegerät = charger
netzteil = power supply = psu
platine = board = pcb
sensor = fühler
motor = antrieb = drive
lötzinn = solder
lötkolben = soldering iron
zange = pliers
seitenschneider = side cutter = cutter
schraubendreher = schraubenzieher = screwdriver
bit = bits
bohrer = drill bit
bohrmaschine = drill
akkuschrauber = cordless drill = drill driver
säge = saw
hammer = mallet
feile = file
schleifpapier = sandpaper = schleifpapier
kleber = glue = adhesive = klebstoff
klebeband = tape = tesa
isolierband = electrical tape
schrumpfschlauch = heat shrink
kabelbinder = cable tie = zip tie
schlauch = hose = tube
rohr = pipe = tube
leiste = strip = batten
profil = profile = extrusion
blech = sheet metal
holz = wood
metall = metal
kunststoff = plastik = plastic
gummi = rubber
dichtung = seal = gasket
feder = spring
kugellager = lager = bearing
riemen = belt
zahnrad = gear
pumpe = pump
ventil = valve
werkzeug = tool
messgerät = meter = gauge
multimeter = voltmeter
schieblehre = messschieber = caliper
wasserwaage = level
schutzbrille = safety glasses = goggles
handschuhe = gloves
maske = mask = atemschutz = respirator
gehörschutz = ear protection = ear muffs
düse = nozzle
filament = faden
harz = resin
drucker = printer
schublade = drawer
kiste = crate = box
regal = shelf
koffer = case
schrank = cabinet
werkbank = workbench
magnet = magnet
schelle = clamp
zwinge = clamp
winkel = bracket = angle
scharnier = hinge
griff = handle
rad = wheel
rolle = roller = pulley
kette = chain
seil = rope
schnur = cord = string
lampe = lamp = light = leuchte
"""
_STEM_SUFFIXES = ("en", "er", "n", "e", "s")


def _groups(text: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for line in text.splitlines():
        words = {w.strip().casefold() for w in line.split("=") if w.strip()}
        if len(words) < 2:
            continue
        merged = set(words)
        for w in words:
            merged |= out.get(w, set())
        for w in merged:
            out[w] = merged
    return out


LEX = _groups(LEXICON)


def stems(term: str) -> set[str]:
    """Einfache Wortstämme für Plural/Fälle: 'schrauben' -> 'schraube', 'schraub'."""
    out = set()
    for suffix in _STEM_SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= 4:
            out.add(term[: -len(suffix)])
    return out


def tokens(q: str, synonyms: dict[str, list[str]]) -> list[str]:
    """Suchwörter; bekannte Mehrwort-Begriffe ('side cutter', 'power supply') bleiben zusammen."""
    words = [w.casefold() for w in q.replace('"', " ").split() if w]
    out: list[str] = []
    i = 0
    while i < len(words):
        for n in (3, 2):
            phrase = " ".join(words[i : i + n])
            if len(words) - i >= n and (phrase in LEX or phrase in synonyms):
                out.append(phrase)
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out


def expand(term: str, synonyms: dict[str, list[str]]) -> list[str]:
    variants = {term} | stems(term)
    for v in list(variants):
        variants |= set(synonyms.get(v, ()))
        variants |= LEX.get(v, set())
    # Mehrwort-Varianten ('power supply') bleiben als Phrase; zu kurze fliegen raus
    return sorted(v for v in variants if len(v) >= 2)


def _query(
    conn: sqlite3.Connection, groups: list[list[str]], limit: int, tag: int | None = None
) -> list[sqlite3.Row]:
    only = " AND item.type_id = ?" if tag else ""
    extra = (tag,) if tag else ()
    if not groups:  # nur Tag-Filter
        return conn.execute(
            f"SELECT * FROM item WHERE archived = 0{only} ORDER BY name COLLATE NOCASE LIMIT ?",
            (*extra, limit),
        ).fetchall()
    if all(len(w) >= 3 for g in groups for w in g):
        match = " AND ".join(
            "(" + " OR ".join('"' + w.replace('"', "") + '"' for w in g) + ")" for g in groups
        )
        return conn.execute(
            "SELECT item.* FROM item_fts JOIN item ON item.id = item_fts.rowid"
            f" WHERE item_fts MATCH ? AND item.archived = 0{only}"
            " ORDER BY bm25(item_fts, 10.0, 6.0, 8.0, 5.0, 1.0) LIMIT ?",
            (match, *extra, limit),
        ).fetchall()
    where = " AND ".join(
        "(" + " OR ".join([f"{SEARCH_TEXT} LIKE ?"] * len(g)) + ")" for g in groups
    )
    return conn.execute(
        f"SELECT * FROM item WHERE {where} AND archived = 0{only} ORDER BY name LIMIT ?",
        (*(f"%{w}%" for g in groups for w in g), *extra, limit),
    ).fetchall()


def vocabulary(conn: sqlite3.Connection) -> set[str]:
    vocab: set[str] = set(LEX)
    for row in conn.execute("SELECT name, full_name, model, tags FROM item WHERE archived = 0"):
        text = " ".join(str(v or "") for v in row)
        vocab.update(w.casefold() for w in re.findall(r"\w{3,}", text))
    for row in conn.execute("SELECT name FROM container"):
        vocab.update(w.casefold() for w in re.findall(r"\w{3,}", row["name"]))
    return vocab


def run(
    conn: sqlite3.Connection,
    q: str,
    synonyms: dict[str, list[str]],
    typo: bool = True,
    limit: int = 50,
    tag: int | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Teile suchen (optional nur mit Tag); gibt (Treffer mit Pfad, korrigierte Suche) zurück."""
    terms = tokens(q, synonyms)
    if not terms:
        rows = _query(conn, [], limit, tag) if tag else []
        return [{**dict(r), "path": path_label(conn, r["container_id"])} for r in rows], None
    groups = [expand(t, synonyms) for t in terms]
    corrected, vocab = list(terms), None
    for i, t in enumerate(terms):
        if not typo or len(t) < 3 or _query(conn, [groups[i]], 1):
            continue
        vocab = vocab if vocab is not None else vocabulary(conn)
        if t in vocab:
            continue
        match = difflib.get_close_matches(t, vocab, n=1, cutoff=0.75)
        if match:
            corrected[i] = match[0]
            groups[i] = expand(match[0], synonyms)
    rows = _query(conn, groups, limit, tag)
    items = [{**dict(r), "path": path_label(conn, r["container_id"])} for r in rows]
    fixed = " ".join(corrected)
    return items, (fixed if fixed != " ".join(terms) else None)


def containers(
    conn: sqlite3.Connection, q: str, synonyms: dict[str, list[str]], limit: int = 20
) -> list[dict[str, Any]]:
    """Behälter nach Name/Notizen (mit Varianten je Wort) oder exaktem Code."""
    terms = [t.casefold() for t in q.split() if t]
    if not terms:
        return []
    groups = [expand(t, synonyms) for t in terms]
    where = " AND ".join(
        "(" + " OR ".join(["fold(name || ' ' || notes) LIKE ?"] * len(g)) + ")" for g in groups
    )
    rows = conn.execute(
        f"SELECT * FROM container WHERE (code = ? OR ({where}))"
        " AND NOT (kind = 'compartment' AND name = 'Fach ' || position) ORDER BY name LIMIT ?",
        (q.strip().upper(), *(f"%{w}%" for g in groups for w in g), limit),
    ).fetchall()
    return [{**dict(r), "path": path_label(conn, r["id"])} for r in rows]
