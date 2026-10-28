"""Kabel (Kategorie CBL): Stecker Seite A, Stecker Seite B, Länge -> einheitlicher Etikett-Name.

`parse` erkennt Kurzformen aus Eingabe/Diktat ('USB A-C 2m', 'Display Port 1.5m', 'LAN 2m',
'USB 2.0 Verlängerung 2m'); `name` baut daraus 'USB-A – USB-C 2m' (max. ~24 Zeichen, D30).
"""

import re

# Schreibweisen -> einheitlicher Steckername
PLUGS = {
    "usb a": "USB-A", "usb-a": "USB-A", "a": "USB-A",
    "usb b": "USB-B", "usb-b": "USB-B", "b": "USB-B",
    "usb c": "USB-C", "usb-c": "USB-C", "c": "USB-C", "typ c": "USB-C", "type c": "USB-C",
    "c90": "USB-C 90°", "usb-c90": "USB-C 90°", "c 90": "USB-C 90°",
    "micro": "Micro-USB", "micro usb": "Micro-USB", "micro-usb": "Micro-USB",
    "microusb": "Micro-USB",
    "mini": "Mini-USB", "mini usb": "Mini-USB", "mini-usb": "Mini-USB",
    "lightning": "Lightning",
    "displayport": "DP", "display port": "DP", "dp": "DP",
    "mini displayport": "Mini-DP", "mini dp": "Mini-DP", "mini-dp": "Mini-DP",
    "hdmi": "HDMI", "mini hdmi": "Mini-HDMI", "micro hdmi": "Micro-HDMI",
    "dvi": "DVI", "vga": "VGA",
    "lan": "RJ45", "rj45": "RJ45", "ethernet": "RJ45", "netzwerk": "RJ45", "patch": "RJ45",
    "patchkabel": "RJ45", "cat5": "RJ45", "cat6": "RJ45", "cat7": "RJ45",
    "klinke": "Klinke", "aux": "Klinke", "3,5mm": "Klinke", "3.5mm": "Klinke",
    "kaltgerät": "C13", "kaltgeräte": "C13", "c13": "C13", "c7": "C7", "c5": "C5",
    "schuko": "Schuko", "sata": "SATA", "molex": "Molex", "xlr": "XLR", "cinch": "Cinch",
    "toslink": "Toslink", "optisch": "Toslink",
    # Netz (230 V) und Drehstrom
    "euro": "Euro-Stecker", "eurostecker": "Euro-Stecker", "euro-stecker": "Euro-Stecker",
    "euro stecker": "Euro-Stecker",
    "cee 7/16": "Euro-Stecker", "typ c stecker": "Euro-Stecker",
    "euro-8": "C7", "euro8": "C7", "c14": "C14", "c15": "C15", "c19": "C19", "c20": "C20",
    "c13 winkel": "C13 90°", "c13 90": "C13 90°", "c13 90°": "C13 90°",
    "schuko winkel": "Schuko 90°", "schuko 90": "Schuko 90°", "schuko 90°": "Schuko 90°",
    "typ f": "Schuko", "cee 7/7": "Schuko",
    "drehstrom": "CEE 16A 5p", "cee": "CEE 16A 5p", "cee 16": "CEE 16A 5p",
    "cee 16a": "CEE 16A 5p", "cee16": "CEE 16A 5p", "cee 16a 5p": "CEE 16A 5p",
    "cee 16a 3p": "CEE 16A 3p", "cee blau": "CEE 16A 3p", "campingstecker": "CEE 16A 3p",
    "cee 32": "CEE 32A 5p", "cee 32a": "CEE 32A 5p", "cee32": "CEE 32A 5p",
    "cee 32a 5p": "CEE 32A 5p", "cee 32a 3p": "CEE 32A 3p", "cee 63a": "CEE 63A",
    "cee 63": "CEE 63A", "perilex": "Perilex", "wieland": "Wieland", "powercon": "powerCON",
    "kfz": "KFZ", "zigarettenanzünder": "KFZ", "bordsteckdose": "KFZ",
    # Gleichstrom / Power Delivery
    "usb pd": "USB-C PD", "usb-c pd": "USB-C PD", "pd": "USB-C PD", "power delivery": "USB-C PD",
    "usb-c 100w": "USB-C PD", "usb-c 240w": "USB-C PD", "thunderbolt": "Thunderbolt",
    "magsafe": "MagSafe", "magsafe 3": "MagSafe 3", "dc": "DC",
    "dc 5,5x2,1": "DC 5,5x2,1", "dc 5.5x2.1": "DC 5,5x2,1", "5,5x2,1": "DC 5,5x2,1",
    "dc 5,5x2,5": "DC 5,5x2,5", "5,5x2,5": "DC 5,5x2,5", "dc 3,5x1,35": "DC 3,5x1,35",
    "dc 4,0x1,7": "DC 4,0x1,7", "dc 2,5x0,7": "DC 2,5x0,7", "dc 7,4x5,0": "DC 7,4x5,0",
    "xt60": "XT60", "xt30": "XT30", "xt90": "XT90", "ec5": "EC5", "tamiya": "Tamiya",
    "anderson": "Anderson", "jst": "JST", "dupont": "Dupont", "bananenstecker": "Banane",
    "banane": "Banane", "krokodilklemme": "Krokodil", "krokodil": "Krokodil",
    "kabelschuh": "Kabelschuh", "aderendhülse": "Aderendhülse", "offen": "offen",
    # Sonstiges
    "rj11": "RJ11", "rj12": "RJ12", "bnc": "BNC", "sma": "SMA", "f-stecker": "F-Stecker",
    "d-sub": "D-Sub", "dsub": "D-Sub", "serial": "D-Sub 9", "rs232": "D-Sub 9", "db9": "D-Sub 9",
    "speakon": "Speakon", "midi": "MIDI", "klinke 6,35": "Klinke 6,35", "6,35mm": "Klinke 6,35",
    "firewire": "FireWire", "scart": "SCART", "peitschenkabel": "offen",
}  # fmt: skip
# Familie + Kurzform: 'USB A-C' -> 'a', 'c' werden als USB-Stecker gelesen
_USB_SHORT = {"a": "USB-A", "b": "USB-B", "c": "USB-C", "c90": "USB-C 90°", "micro": "Micro-USB",
              "mini": "Mini-USB"}  # fmt: skip
# Länge am Ende, als eigenständige Zahl ('2m', '1,5 m', '150cm', '2.5'); '3x1,5' zählt nicht
_LENGTH = re.compile(r"(?:^|(?<=\s))(\d+(?:[.,]\d+)?)\s*(cm|m)?\s*$", re.IGNORECASE)
_STANDARD = re.compile(r"\b(usb\s*[234](?:\.\d)?|dp\s*1\.\d|hdmi\s*2\.\d|cat\s*\d[a-z]?)\b", re.I)
_SIDES = re.compile(r"\s*(?:-|–|>|/|\bauf\b|\bzu\b|\bto\b)\s*", re.IGNORECASE)
_EXTENSION = re.compile(r"\bverlängerung\b|\bextension\b", re.IGNORECASE)


_KNOWN = set(PLUGS.values()) | set(_USB_SHORT.values())


def plug(raw: str) -> str:
    key = " ".join(raw.casefold().replace("_", " ").split())
    return PLUGS.get(key, PLUGS.get(key.replace(" ", ""), raw.strip()))


def _usb_side(raw: str) -> str:
    """Seite nach 'USB …': Kurzform (A, C, Micro), sonst bekannter Stecker (HDMI), sonst USB-…"""
    if (short := raw.casefold().replace(" ", "")) in _USB_SHORT:
        return _USB_SHORT[short]
    key = " ".join(raw.casefold().split())
    if key in PLUGS and len(key) > 1:
        return PLUGS[key]
    usb = plug("usb " + raw)
    return usb if usb in _KNOWN else raw.strip()  # unbekannt: so lassen, wie eingegeben


def parse(text: str) -> dict[str, str]:
    """'USB A-C 2.5' -> {plug_a: USB-A, plug_b: USB-C, length: 2.5}; unbekannt -> {}."""
    s = " ".join(text.split())
    out: dict[str, str] = {}
    unit = ""
    if m := _LENGTH.search(s):
        value = float(m.group(1).replace(",", "."))
        unit = (m.group(2) or "").lower()
        if unit == "cm":
            value /= 100
        if 0 < value <= 100:
            out["length"] = f"{value:g}"
            s = s[: m.start()].strip()
    usb_family = s.casefold().startswith("usb")
    if std := _STANDARD.search(s):
        found = " ".join(std.group(1).upper().split())
        out["standard"] = re.sub(r"^CAT\s*", "Cat", found)
        s = (s[: std.start()] + s[std.end() :]).strip()
    extension = bool(_EXTENSION.search(s))
    s = _EXTENSION.sub("", s).strip(" -")
    # Bindestrich in Steckernamen ist kein Trenner: 'USB-C', 'Micro-USB', 'Mini-DP'
    s = re.sub(r"\b(usb|micro|mini|euro)-(?=\w)", r"\1 ", s, flags=re.IGNORECASE)
    words = s.split()
    family = words[0].casefold() if words else ""
    if usb_family and family != "usb":  # 'USB 2.0 Verlängerung': Familie stand vor dem Standard
        family, words = "usb", ["usb", *words]
    rest = " ".join(words[1:]) if family == "usb" else s
    sides = [p.strip() for p in _SIDES.split(rest) if p.strip()]
    if family == "usb":
        sides = [_usb_side(p) for p in sides]
        if not sides:
            sides = ["USB-A"]  # 'USB 2.0 Verlängerung' -> USB-A
    else:
        sides = [plug(p) for p in sides]
    if not any(side in _KNOWN for side in sides):  # z. B. 'NYM-J 3x1,5': keine Steckerkabel
        if not unit:
            out.pop("length", None)  # Zahl ohne Einheit ist dann keine sichere Länge
        return out
    a = sides[0]
    b = sides[1] if len(sides) > 1 else a  # 'HDMI 2m', 'USB C 1m' -> gleicher Stecker beidseitig
    if len(sides) == 1 and a == "C13":  # Kaltgerätekabel
        a, b = "Schuko", "C13"
    if len(sides) == 1 and a in ("C7", "C5", "C15"):  # Geräte-Netzkabel
        a, b = ("Euro-Stecker" if a == "C7" else "Schuko"), a
    if len(sides) == 1 and a in ("Micro-USB", "Mini-USB", "Lightning"):  # Lade-/Datenkabel
        a, b = "USB-A", a
    if extension:
        b = f"{a} Buchse"
    out.update(plug_a=a, plug_b=b)
    return out


def name(specs: dict[str, str]) -> str:
    """Etikett-Name: 'USB-A – USB-C 2,5m'; ohne Stecker A -> ''."""
    a, b = specs.get("plug_a", "").strip(), specs.get("plug_b", "").strip()
    if not a:
        return ""
    length = specs.get("length", "").strip().replace(".", ",")
    text = f"{a} – {b}" if b else a
    return f"{text} {length}m" if length else text


def full_name(specs: dict[str, str]) -> str:
    """'Kabel USB-A auf USB-C, 2 m (USB 2.0)' für das Feld „Vollständiger Name“."""
    a, b = specs.get("plug_a", ""), specs.get("plug_b", "")
    if not a:
        return ""
    text = f"Kabel {a} auf {b}" if b and b != a else f"Kabel {a}"
    if length := specs.get("length", ""):
        text += f", {length.replace('.', ',')} m"
    if std := specs.get("standard", ""):
        text += f" ({std})"
    return text


# Reihenfolge für die Auswahlliste auf Start: häufige Stecker zuerst
COMMON = [
    "USB-A", "USB-C", "Micro-USB", "USB-B", "USB-C 90°", "Mini-USB", "Lightning",
    "HDMI", "Mini-HDMI", "Micro-HDMI", "DP", "Mini-DP", "DVI", "VGA", "RJ45",
    "Klinke", "Cinch", "XLR", "Toslink", "SATA", "Molex",
    # Netz 230 V
    "Schuko", "Euro-Stecker", "C13", "C14", "C7", "C5", "C15", "C19", "C20",
    "Schuko 90°", "C13 90°",
    # Drehstrom / Industrie
    "CEE 16A 5p", "CEE 32A 5p", "CEE 16A 3p", "CEE 32A 3p", "CEE 63A", "Perilex", "Wieland",
    "powerCON",
    # Power Delivery und Gleichstrom
    "USB-C PD", "Thunderbolt", "MagSafe", "MagSafe 3", "DC 5,5x2,1", "DC 5,5x2,5",
    "DC 3,5x1,35", "DC 4,0x1,7", "DC 2,5x0,7", "DC 7,4x5,0", "KFZ", "XT60", "XT30", "XT90",
    "EC5", "Anderson", "Tamiya", "JST", "Dupont", "Banane", "Krokodil", "Kabelschuh",
    "Aderendhülse", "offen",
    # Sonstiges
    "RJ11", "RJ12", "BNC", "SMA", "F-Stecker", "D-Sub", "D-Sub 9", "Speakon", "MIDI",
    "Klinke 6,35", "FireWire", "SCART",
]  # fmt: skip
