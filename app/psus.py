"""Netzteile (Kategorie PSU): Spannung, Strom, Stecker -> einheitlicher Etikett-Name.

`parse` erkennt '12V 2A 5,5x2,1', 'Netzteil 5 V 3000 mA USB-C'; `name` baut 'Netzteil 12V 2A USB-C'
(bei Überlänge 'NT …', max. ~24 Zeichen für das 40×12-Etikett).
"""

import re

from app import cables

_VOLT = re.compile(r"(\d+(?:[.,]\d+)?)\s*v\b", re.IGNORECASE)
_AMP = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m?a)\b", re.IGNORECASE)
_WATT = re.compile(r"(\d+(?:[.,]\d+)?)\s*w\b", re.IGNORECASE)
_BARREL = re.compile(r"(\d[.,]\d)\s*[x×/]\s*(\d[.,]\d)")  # Hohlstecker 5,5x2,1
TEXT_MAX = 24


def _num(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def fmt(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def plug(raw: str) -> str:
    """Stecker vereinheitlichen; Hohlstecker als 'DC 5,5x2,1'."""
    if m := _BARREL.search(raw):
        return f"DC {m.group(1).replace('.', ',')}x{m.group(2).replace('.', ',')}"
    if re.search(r"hohl|barrel|dc\b", raw, re.IGNORECASE):
        return "DC"
    return cables.plug(raw)


def parse(text: str) -> dict[str, str]:
    """'Netzteil 12V 2A 5,5x2,1' -> {volt: 12, amp: 2, plug: DC 5,5x2,1}."""
    out: dict[str, str] = {}
    s = text
    if m := _BARREL.search(s):
        out["plug"] = plug(m.group(0))
        s = s[: m.start()] + s[m.end() :]
    if m := _VOLT.search(s):
        out["volt"] = f"{_num(m.group(1)):g}"
        s = s[: m.start()] + s[m.end() :]
    if m := _AMP.search(s):
        amp = _num(m.group(1)) or 0
        out["amp"] = f"{amp / 1000 if m.group(2).lower() == 'ma' else amp:g}"
        s = s[: m.start()] + s[m.end() :]
    if m := _WATT.search(s):
        out["watt"] = f"{_num(m.group(1)):g}"
        s = s[: m.start()] + s[m.end() :]
    if "plug" not in out:
        rest = re.sub(
            r"\b(netzteil|steckernetzteil|ladegerät|power supply|psu|nt)\b", " ", s, flags=re.I
        )
        for word in re.split(r"[\s,;]+", rest):
            if word and ((p := plug(word)) in cables._KNOWN or p == "DC"):
                out["plug"] = p
                break
    return out


def complete(specs: dict[str, str]) -> dict[str, str]:
    """Leistung aus Spannung × Strom ergänzen, wenn nicht angegeben."""
    out = dict(specs)
    volt, amp = _num(out.get("volt", "")), _num(out.get("amp", ""))
    if not out.get("watt") and volt and amp:
        out["watt"] = f"{round(volt * amp, 1):g}"
    return out


def name(specs: dict[str, str]) -> str:
    """'Netzteil 12V 2A DC 5,5x2,1' bzw. kürzer 'NT 12V 2A DC 5,5x2,1'; ohne Spannung -> ''."""
    volt, amp = _num(specs.get("volt", "")), _num(specs.get("amp", ""))
    if volt is None:
        return ""
    parts = [f"{fmt(volt)}V"]
    if amp is not None:
        parts.append(f"{fmt(amp)}A")
    if p := specs.get("plug", "").strip():
        parts.append(p)
    text = "Netzteil " + " ".join(parts)
    return text if len(text) <= TEXT_MAX else "NT " + " ".join(parts)


def full_name(specs: dict[str, str]) -> str:
    """'Netzteil 12 V, 2 A, 24 W, Stecker DC 5,5x2,1' für „Vollständiger Name“."""
    if not specs.get("volt"):
        return ""
    bits = [f"{fmt(_num(specs['volt']) or 0)} V"]
    if specs.get("amp"):
        bits.append(f"{fmt(_num(specs['amp']) or 0)} A")
    if specs.get("watt"):
        bits.append(f"{fmt(_num(specs['watt']) or 0)} W")
    if specs.get("plug"):
        bits.append(f"Stecker {specs['plug']}")
    return "Netzteil " + ", ".join(bits)
