"""Arbeitspaket 2 „Typen“: Bereich › Gruppe › Typ, neue Typen, Erkennung, API."""

import re

from fastapi.testclient import TestClient

from app import catalog, codes

# Stand 1.3: Schlüssel, Code-Präfix und Feld-Schlüssel der 71 bisherigen Typen. Sie stehen in
# der Datenbank (item.ctype/cfields) und dürfen sich nicht ändern; neue Felder sind erlaubt.
OLD = {
    "schraube": ("CNS", "head thread length drive finish standard strength coating pitch threadlen pack node brand source"),
    "mutter": ("CNS", "kind thread finish standard strength coating pitch threadlen pack node brand source"),
    "insert": ("CNS", "kind thread length od node material shape mount hole wall through pitch pullout standard color brand source strength coating threadlen pack"),
    "scheibe": ("CNS", "kind thread od thickness finish standard strength coating pitch threadlen pack node brand source"),
    "holzschraube": ("CNS", "brand dia length head drive standard strength coating pitch threadlen pack node source"),
    "duebel": ("CNS", "kind size standard strength coating pitch threadlen pack node brand source"),
    "gewindestange": ("CNS", "kind thread length standard strength coating pitch threadlen pack node brand source"),
    "kleinteil": ("CNS", "kind size standard strength coating pitch threadlen pack node brand source"),
    "kleber": ("CNS", "kind brand content cure temp color source"),
    "klebeband": ("CNS", "kind width content cure temp color brand source"),
    "loeten": ("CNS", "kind size content cure temp color brand source"),
    "schmierung": ("CNS", "kind content cure temp color brand source"),
    "batterie": ("CNS", "kind brand content cure temp color source"),
    "schleifen": ("CNS", "kind grit content cure temp color brand source"),
    "lager": ("CNS", "kind size material load standard brand source"),
    "kupplung": ("CNS", "kind size material load standard brand source"),
    "pneumatik": ("CNS", "kind dia thread material load standard brand source"),
    "magnet": ("CNS", "kind size material load standard brand source"),
    "profil": ("CNS", "kind size material load standard brand source"),
    "schrumpf": ("CNS", "dia color rated rvolt brand source"),
    "huelse": ("CNS", "size color rated rvolt brand source"),
    "kabelschuh": ("CNS", "kind size color rated rvolt brand source"),
    "klemme": ("CNS", "kind poles color rated rvolt brand source"),
    "sicherung": ("CNS", "kind amp color rated rvolt brand source"),
    "mcu": ("CMP", "kind model interface package tolerance rating brand source"),
    "sensor": ("CMP", "kind model interface package tolerance rating brand source"),
    "aktor": ("CMP", "kind model voltage package tolerance rating brand source"),
    "anzeige": ("CMP", "kind interface package tolerance rating brand source"),
    "schalter": ("CMP", "kind model package tolerance rating brand source"),
    "treiber": ("CMP", "kind model package tolerance rating brand source"),
    "strom": ("CMP", "kind model voltage package tolerance rating brand source"),
    "funk": ("CMP", "kind model package tolerance rating brand source"),
    "led": ("CMP", "kind color package tolerance rating brand source"),
    "passiv": ("CMP", "kind value package tolerance rating brand source"),
    "halbleiter": ("CMP", "kind model package tolerance rating brand source"),
    "stecker": ("CMP", "kind pins package tolerance rating brand source"),
    "proto": ("CMP", "kind size package tolerance rating brand source"),
    "smarthome": ("CMP", "kind brand package tolerance rating source"),
    "zange": ("TOL", "kind brand size material source"),
    "schrauber": ("TOL", "kind size material brand source"),
    "bohrer": ("TOL", "kind size material brand source"),
    "messen": ("TOL", "kind size material brand source"),
    "schneiden": ("TOL", "kind size material brand source"),
    "werkzeug_sonst": ("TOL", "kind brand size material source"),
    "duese": ("CMP", "kind size model compat material brand source"),
    "druckerteil": ("CMP", "kind model compat material brand source"),
    "netzteil": ("CMP", "kind volt amp plug model compat material brand source"),
    "laser": ("CMP", "kind model compat material brand source"),
    "etiketten": ("CNS", "kind size compat material brand source"),
    "netzwerkkabel": ("CMP", "kind length color shield brand source"),
    "rj45": ("CMP", "kind cat color brand source"),
    "netzwerkgeraet": ("CMP", "kind model color brand source"),
    "holz": ("RAW", "kind size dims material color brand source"),
    "metall": ("RAW", "kind form size dims material color brand source"),
    "kabel": ("ART", "kind ends length color rated rvolt brand source"),
    "gridfinity": ("ART", "kind size height color compat material brand source"),
    "bohrersatz": ("ART", "kind detail brand size material source"),
    "heissleim": ("ART", "kind size content cure temp color brand source"),
    "farbe": ("ART", "kind color size content cure temp brand source"),
    "kabelbinder": ("ART", "kind size color rated rvolt brand source"),
    "akku": ("ART", "kind cap volt package tolerance rating brand source"),
    "gehaeuse": ("ART", "kind size package tolerance rating brand source"),
    "buero": ("ART", "name content cure temp color brand source"),
    "allgemein": ("ART", "name dims material color brand source"),
    "filament": ("FIL", "brand plastic additive additive_pct color diameter weight spool_type spool_weight price source"),
    "harz": ("RES", "brand material color volume bottle_weight price source"),
    "steckernetzteil": ("PSU", "volt amp plug input color rated rvolt brand source"),
    "kabel_stecker": ("CBL", "plug_a plug_b length color rated rvolt brand source"),
    "werkzeug_allg": ("TOL", "kind brand size material source"),
    "ppe": ("PPE", "kind size material brand source"),
    "norb16_bin": ("ART", "size state compat material brand source"),
}  # fmt: skip


def test_old_keys_prefixes_and_fields_unchanged() -> None:
    assert len(OLD) == 71
    for key, (cat, fields) in OLD.items():
        t = catalog.BY_KEY[key]
        assert t.cat == cat, key
        have = [f.key for f in t.fields]
        assert have[: len(fields.split())] == fields.split(), key


def test_all_types_valid() -> None:
    keys = [t.key for t in catalog.TYPES]
    assert len(keys) == len(set(keys))
    assert len(catalog.TYPES) >= len(OLD) + 40
    assert len(catalog.TYPES_2_0) >= 40
    for t in catalog.TYPES:
        assert re.fullmatch(r"[a-z0-9_]+", t.key), t.key
        assert t.cat in codes.ITEM_PREFIXES, t.key
        assert t.group in catalog.GROUPS, t.key
        assert t.extras in catalog.EXTRAS, t.key
        assert len({f.key for f in t.fields}) == len(t.fields), t.key
        values = {f.key: (f.options[0] if f.options else "X") for f in t.fields}
        assert catalog.name(t, values).strip(), t.key
    for t in catalog.TYPES_2_0:  # neue Typen: 2–5 Hauptfelder, Namen etikettentauglich kurz
        main = [f for f in catalog.BY_KEY[t.key].fields if not f.extra]
        assert 2 <= len(main) <= 5, t.key
        values = {f.key: (f.options[0] if f.options else "X") for f in main}
        assert len(catalog.name(t, values)) <= 45, t.key


def test_areas_two_levels() -> None:
    assert 6 <= len(catalog.AREAS) <= 9
    assert len(catalog.GROUPS) == len(set(catalog.GROUPS))
    tree = catalog.areas()
    assert [a for a, _ in tree] == [a for a, _ in catalog.AREAS]  # kein Bereich leer
    for _a, groups in tree:
        assert all(ts for _g, ts in groups)
    counted = sum(len(ts) for _a, gs in tree for _g, ts in gs)
    assert counted == len(catalog.TYPES)
    assert catalog.area_of(catalog.BY_KEY["schraube"]) == "Befestigung"
    assert catalog.area_of(catalog.BY_KEY["passiv"]) == "Elektronik"


def test_field_keys_of_new_types_and_names() -> None:
    t = catalog.BY_KEY["dichtung"]
    assert catalog.name(t, {"kind": "O-Ring", "id": "10", "cs": "2", "material": "NBR"}) == (
        "O-Ring 10x2 NBR"
    )
    t = catalog.BY_KEY["werkzeugakku"]
    assert catalog.name(t, {"brand": "Makita LXT", "volt": "18", "cap": "5"}) == (
        "Akku Makita LXT 18V 5Ah"
    )
    t = catalog.BY_KEY["laserplatte"]
    vals = {"kind": "Pappel-Sperrholz", "thickness": "3", "size": "300x400"}
    assert catalog.name(t, vals) == "Pappel-Sperrholz 3mm 300x400"


def test_guess_old_names_unchanged() -> None:
    cases = {
        "Zylinderkopfschraube M3x10": "schraube", "Widerstand 10k": "passiv",
        "Sechskantmutter M4": "mutter", "Senkkopfschraube M4x20": "schraube",
        "Kugellager 608": "lager", "GT2 Riemen 6mm": "kupplung", "18650 Akku": "batterie",
        "Schrumpfschlauch 3.0": "schrumpf", "Spax 4x40": "holzschraube",
        "Steckernetzteil 9V 1A DC 5,5x2,5": "steckernetzteil", "DC-Buchse 5-polig": "stecker",
        "WAGO 221 3-polig": "klemme", "Lötzinn 0.8 mm": "loeten", "Neodym Scheibe 10x3": "magnet",
    }  # fmt: skip
    for text, key in cases.items():
        assert (catalog.guess(None, text) or ("",))[0] == key, text
    assert catalog.guess(None, "Akkuschrauber") is None


def test_guess_new_types() -> None:
    cases = {
        "O-Ring 10x2": "dichtung", "Druckfeder Ø8 L20": "feder", "Blindniete 4x10": "niete",
        "Schlauchschelle 12-22": "schelle", "Zahnriemen GT2 6mm": "zahnriemen",
        "Trapezmutter Tr8x8": "spindel", "Linearwelle 8x300": "linear",
        "Schrittmotor NEMA17": "motor", "Lüfter 5015 24V": "luefter", "Quarz 16 MHz": "quarz",
        "Akku Makita 18V 5Ah": "werkzeugakku", "LED-Lampe E27 9W": "leuchtmittel",
        "Isopropanol 99%": "reiniger", "Heizpatrone 24V 40W": "heizung",
        "Stichsägeblatt Holz": "saegeblatt", "Trennscheibe 125": "trennscheibe",
        "Pappel-Sperrholz 3mm 300x400": "laserplatte", "FFP2-Maske": "atemschutz",
        "Feuerlöscher 6kg": "brandschutz", "Kapselgehörschutz SNR 30": "gehoerschutz",
        "Gewindebohrer M3": "gewindebohrer", "microSD 32GB": "speicher",
    }  # fmt: skip
    for text, key in cases.items():
        assert (catalog.guess(None, text) or ("",))[0] == key, text
    g = catalog.guess(None, "O-Ring 10x2")
    assert g is not None and g[1]["id"] == "10" and g[1]["cs"] == "2"


def test_neu_page_shows_areas_groups_types(client: TestClient) -> None:
    page = client.get("/neu?typ=feder").text
    areas = re.findall(r'<details class="area"[^>]*data-a="([^"]+)"', page)
    assert areas[:2] == ["Befestigung", "Mechanik &amp; Antrieb"] and len(areas) == 9
    assert re.search(r'data-a="Mechanik &amp; Antrieb" open', page)  # Bereich des Typs offen
    assert not re.search(r'data-a="Befestigung" open', page)
    assert "<h3>Federn, Dichtungen &amp; Pneumatik</h3>" in page
    assert 'href="/neu?typ=feder" class="on"' in page
    assert 'class="neu-types type-tree"' in page and 'id="type-filter"' in page


def test_custom_types_get_own_area(client: TestClient) -> None:
    client.post("/sortiment/eigene", data={"label": "Kerze", "fields": "Duft"})
    page = client.get("/neu?typ=schraube").text
    assert page.index('data-a="Haus &amp; Schutz"') < page.index('data-a="Eigene Typen"')
    assert "Kerze" in page


def test_sortiment_shows_areas_and_search(client: TestClient) -> None:
    page = client.get("/sortiment").text
    assert 'id="type-filter"' in page and 'class="type-tree sort-tree"' in page
    assert 'data-a="Befestigung"' in page and 'data-g="Schrauben &amp; Muttern"' in page
    assert 'data-a="Material &amp; Datenblatt"' in page
    assert page.count('href="/sortiment/schraube"') == 1
    assert 'href="/sortiment/zahnriemen"' in page


def test_api_catalog_has_area(client: TestClient) -> None:
    rows = client.get("/api/v1/types/catalog").json()
    by_key = {r["key"]: r for r in rows}
    assert by_key["schraube"]["area"] == "Befestigung"
    assert by_key["schraube"]["group"] == "Schrauben & Muttern"
    assert by_key["zahnriemen"]["area"] == "Mechanik & Antrieb"
    assert len(rows) == len({r["key"] for r in rows})
