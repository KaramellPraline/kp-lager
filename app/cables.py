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
    return PLUGS[key] if key in PLUGS and len(key) > 1 else plug("usb " + raw)


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
    s = re.sub(r"\b(usb|micro|mini)-(?=\w)", r"\1 ", s, flags=re.IGNORECASE)
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
