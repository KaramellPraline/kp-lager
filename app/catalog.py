# ruff: noqa: E501
"""Teile-Katalog: häufige Teile (Heimwerken, 3D-Druck, Laser, Elektronik) mit Auswahlfeldern.

Jeder Typ hat Felder (Auswahl + freie Eingabe) und eine Namensvorlage; daraus entsteht der
Teilename wie im Lager üblich („Zylinderkopfschraube M3x10“, „Holzinsert M4“). Es geht um
schnelles Anlegen, nicht um exakte Erfassung – Details lassen sich am Teil nachtragen.
"""

import contextlib
import json
import re
import sqlite3
from dataclasses import dataclass, replace

from app import codes, materials, repo
from app.repo import LagerError


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    options: tuple[str, ...] = ()
    unit: str = ""
    hint: str = ""
    extra: bool = False  # optional: im Formular unter „Weitere Angaben“ eingeklappt
    row: str = ""  # gleiche Zeilen-Kennung hintereinander = nebeneinander im Formular


@dataclass(frozen=True)
class Type:
    key: str
    group: str
    label: str
    cat: str  # Code-Präfix (CNS, CMP, TOL, RAW, ART)
    fields: tuple[Field, ...]
    parts: tuple[
        tuple[str, ...], ...
    ]  # je Teil Alternativen, z. B. ("{thread}x{length}", "{thread}")
    cmp: bool = False  # Elektronik: Felder landen im Datenblatt (Profil „Elektronikbauteil“)
    material: str = (
        ""  # fil/res/psu/cbl: Felder landen zusätzlich in den Materialdaten (Datenblatt)
    )
    single: bool = False  # Einzelstücke: jede Spule/Flasche eigenes Teil mit eigenem Code
    label_lines: tuple[str, ...] = ()  # Etikett: Zeile 1 (Typ + Spezifikation), Zeile 2 (Maße)
    extras: str = "basis"  # Profil der Zusatzfelder („Weitere Angaben“), siehe EXTRAS


def F(
    key: str,
    label: str,
    options: str = "",
    unit: str = "",
    hint: str = "",
    extra: bool = False,
    row: str = "",
) -> Field:
    opts = tuple(o.strip() for o in options.split("|") if o.strip())
    return Field(key, label, opts, unit, hint, extra, row)


def default_label_layout(t: Type) -> dict[str, object]:
    """Standard-Etikett, dreizeilig: Typ + Spezifikation · Maße · Code (QR links).

    Typen ohne eigene `label_lines` leiten es aus der Namensvorlage ab: die ersten ein bis zwei
    Teile (Art, Gewinde) oben, der Rest als Maße. Leere Felder lassen ihre Zeile entfallen."""
    if t.label_lines:
        first, second = t.label_lines
    else:
        tpl = [alts[0] if not isinstance(alts, str) else alts for alts in t.parts]
        cut = 2 if len(tpl) >= 3 else 1
        first, second = " ".join(tpl[:cut]), " ".join(tpl[cut:])
    lines = [{"t": first, "w": 2, "a": "center"}]
    if second:
        lines.append({"t": second, "w": 2, "a": "center"})
    lines.append({"t": "{code}", "w": 1, "a": "center"})
    return {"qr": "left", "lines": lines}


THREAD = "M2|M2.5|M3|M4|M5|M6|M8|M10|M12"
LENGTH = "4|5|6|8|10|12|16|20|25|30|35|40|50|60"

# Gliederung: Bereich › Gruppe › Typ. Die Reihenfolge hier ist die Anzeige-Reihenfolge; die
# Reihenfolge in TYPES bleibt fest (bei Gleichstand gewinnt in `guess` der frühere Typ).
AREAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Befestigung", ("Schrauben & Muttern", "Dübel, Nieten & Stifte", "Schellen, Haken & Beschläge")),
    ("Mechanik & Antrieb", ("Lager & Führung", "Antrieb & Bewegung", "Federn, Dichtungen & Pneumatik", "Profile & Magnete")),
    ("Elektronik", ("Bauteile", "Module & Boards", "Prototyping & Gehäuse")),
    ("Elektrik & Strom", ("Kabel & Leitungen", "Verbinden & Installation", "Akkus & Netzteile")),
    ("Werkzeug & Messen", ("Handwerkzeug", "Bohren, Fräsen & Sägen", "Schleifen & Trennen", "Messen & Sets")),
    ("3D-Druck & Laser", ("Filament & Harz", "Druckerteile", "Laser", "Ordnung & Etiketten")),
    ("Material & Chemie", ("Holz, Metall & Kunststoff", "Kleben & Dichten", "Löten, Schmieren & Reinigen", "Farbe & Oberfläche")),
    ("Netzwerk & IT", ("Netzwerk", "Computer & Speicher")),
    ("Haus & Schutz", ("Schutzausrüstung", "Sicherheit & Erste Hilfe", "Haushalt, Licht & Sonstiges")),
)  # fmt: skip
GROUPS: tuple[str, ...] = tuple(g for _a, gs in AREAS for g in gs)
AREA_OF: dict[str, str] = {g: a for a, gs in AREAS for g in gs}

TYPES: tuple[Type, ...] = (
    Type(
        "schraube",
        "Schrauben & Muttern",
        "Schraube (Maschinenschraube)",
        "CNS",
        (
            F(
                "head",
                "Kopf / Art",
                "Zylinderkopfschraube|Senkkopfschraube|Linsenkopfschraube|"
                "Flachkopfschraube|Madenschraube|Sechskantschraube|Flanschschraube|Gewindestift",
            ),
            F("thread", "Gewinde", THREAD),
            F("length", "Länge", LENGTH, "mm"),
            F("drive", "Antrieb", "Innensechskant|Torx|Kreuz|Schlitz|Außensechskant"),
            F(
                "finish",
                "Material / Oberfläche",
                "Schwarz 12.9|A2 Edelstahl|A4 Edelstahl|Verzinkt|Messing",
            ),
        ),
        (("{head}",), ("{thread}x{length}", "{thread}")),
        label_lines=("{head} {thread}", "{length}mm {drive}"),
        extras="befestigung",
    ),
    Type(
        "mutter",
        "Schrauben & Muttern",
        "Mutter",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Sechskantmutter|Sicherungsmutter|Flanschmutter|Vierkantmutter (Square Nut)|"
                "Hammermutter|Nutenstein|Flügelmutter|Hutmutter|Rändelmutter",
            ),
            F("thread", "Gewinde", THREAD),
            F("finish", "Material", "Schwarz|Edelstahl|Verzinkt|Messing"),
        ),
        (("{kind}",), ("{thread}",)),
        label_lines=("{kind} {thread}", "{finish}"),
        extras="befestigung",
    ),
    Type(
        "insert",
        "Schrauben & Muttern",
        "Einschmelzmutter / Insert",
        "CNS",
        (
            F("kind", "Art", "Heat-Set Insert|Holzinsert|Aluinsert|Einpressmutter|Gewindeeinsatz"),
            F("thread", "Gewinde", THREAD),
            F("length", "Länge", "3|4|5|6|8|10|12", "mm"),
            F("od", "Außendurchmesser", "4|4.6|5|5.6|6|7|8|9|10|12", "mm"),
            F(
                "node",
                "Node (Nut-Typ / Einbauort)",
                "Nut 5|Nut 6|Nut 8|Nut 10|Profil 2020|Profil 3030|Profil 4040|Holz|"
                "3D-Druckteil|Blech|Kunststoff",
                hint="für welchen Node / welche Nut",
            ),
            F(
                "material",
                "Material",
                "Messing|Edelstahl|Aluminium|Stahl verzinkt|Bronze",
                extra=True,
            ),
            F(
                "shape",
                "Form",
                "Rund|Sechskant|Rändel gerade|Rändel Diamant|Flansch|Konisch",
                extra=True,
            ),
            F(
                "mount",
                "Einbau",
                "Einschmelzen (Heat-Set)|Einpressen|Eindrehen|Einschlagen|Ultraschall|Einkleben",
                extra=True,
            ),
            F("hole", "Bohrung / Aufnahme", "3|3.2|4|4.2|4.5|5|5.6|6|8", "mm", extra=True),
            F("wall", "Mindest-Wandstärke", "", "mm", extra=True),
            F("through", "Gewinde", "Durchgehend|Sackloch", extra=True),
            F("pitch", "Steigung", "Regelgewinde|Feingewinde", extra=True),
            F("pullout", "Auszugskraft", "", "N", extra=True),
            F(
                "standard",
                "Norm / Serie",
                "DIN 7965|DIN 16903|DIN 985|CNC Kitchen|Voron",
                extra=True,
            ),
            F("color", "Farbe / Oberfläche", "Natur|Schwarz|Vernickelt|Eloxiert", extra=True),
            F("brand", "Hersteller / Marke", extra=True),
            F("source", "Bezugsquelle / Art.-Nr.", extra=True),
        ),
        (("{kind}",), ("{thread}",), ("L{length}",), ("Ø{od}",)),
        label_lines=("{kind} {thread}", "{length} x {od}mm"),
        extras="befestigung",
    ),
    Type(
        "scheibe",
        "Schrauben & Muttern",
        "Unterlegscheibe",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Unterlegscheibe|Karosseriescheibe|Fächerscheibe|Federring|Nylonscheibe|"
                "Sicherungsscheibe",
            ),
            F("thread", "Für Gewinde", THREAD),
            F("od", "Außendurchmesser", "5|6|7|8|9|10|12|16|20|24", "mm"),
            F("thickness", "Dicke", "0.5|0.8|1|1.6|2|2.5|3", "mm"),
            F("finish", "Material", "Edelstahl|Verzinkt|Nylon|Messing"),
        ),
        (("{kind}",), ("{thread}",), ("Ø{od}",), ("{thickness}mm",)),
        label_lines=("{kind} {thread}", "Ø{od} x {thickness}mm"),
        extras="befestigung",
    ),
    Type(
        "holzschraube",
        "Schrauben & Muttern",
        "Holzschraube (Spax)",
        "CNS",
        (
            F("brand", "Marke", "Spax|Schnellbauschraube|Spanplattenschraube"),
            F("dia", "Durchmesser", "3|3.5|4|4.5|5|6", "mm"),
            F("length", "Länge", "16|20|25|30|35|40|50|60|70|80|100", "mm"),
            F("head", "Kopf", "Senkkopf|Tellerkopf|Halbrundkopf"),
            F("drive", "Antrieb", "Torx|Kreuz PZ"),
        ),
        (("{brand}",), ("{dia}x{length}",), ("{head}",)),
        label_lines=("{brand} {head}", "{dia} x {length}mm"),
        extras="befestigung",
    ),
    Type(
        "duebel",
        "Dübel, Nieten & Stifte",
        "Dübel",
        "CNS",
        (
            F("kind", "Art", "Spreizdübel|Universaldübel|Holzdübel|Hohlraumdübel|Rahmendübel"),
            F("size", "Maße", "5x25|6x30|8x40|10x50|6x30 Holz|8x40 Holz", "mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="befestigung",
    ),
    Type(
        "gewindestange",
        "Schrauben & Muttern",
        "Gewindestange / Stift",
        "CNS",
        (
            F("kind", "Art", "Gewindestange|Passstift|Stahlstift|Splint|Niete"),
            F("thread", "Gewinde / Ø", THREAD),
            F("length", "Länge", "100|200|300|500|1000", "mm"),
        ),
        (("{kind}",), ("{thread}x{length}", "{thread}")),
        extras="befestigung",
    ),
    Type(
        "kleinteil",
        "Schellen, Haken & Beschläge",
        "Kleinteil (Klett, Gleiter, Kabelbinder …)",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Kabelbinder|Klett|Filzgleiter|Gummifuß|Rändelschraube|Kabelclip|Haken|Öse|Scharnier",
            ),
            F("size", "Maß / Variante", "", hint="z. B. 3x150, 20 mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="befestigung",
    ),
    Type(
        "kleber",
        "Kleben & Dichten",
        "Klebstoff",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Sekundenkleber|Alleskleber|2K-Epoxid|Heißkleber (Sticks)|Holzleim|Gewindekleber|Silikon|Montagekleber",
            ),
            F("brand", "Marke", "UHU|Pattex|Loctite|Bosch|Weicon"),
        ),
        (("{kind}",), ("{brand}",)),
        extras="verbrauch",
    ),
    Type(
        "klebeband",
        "Kleben & Dichten",
        "Klebeband",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Doppelseitig|Kapton|Alu|Gewebeband|Malerkrepp|Isolierband|Teflon|Filament-Tape|Schaumstoff",
            ),
            F("width", "Breite", "6|10|12|19|25|38|50", "mm"),
        ),
        (("Klebeband {kind}", "Klebeband"), ("{width}mm",)),
        extras="verbrauch",
    ),
    Type(
        "loeten",
        "Löten, Schmieren & Reinigen",
        "Löten (Zinn, Flussmittel …)",
        "CNS",
        (
            F("kind", "Art", "Lötzinn|Flussmittel|Entlötlitze|Lötfett|Lötspitze|Wärmeleitpaste"),
            F("size", "Stärke / Variante", "0.5 mm|0.8 mm|1.0 mm|100 g|250 g|bleifrei"),
        ),
        (("{kind}",), ("{size}",)),
        extras="verbrauch",
    ),
    Type(
        "schmierung",
        "Löten, Schmieren & Reinigen",
        "Öl / Fett / Reiniger",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Maschinenöl|Lithiumfett|PTFE-Fett|Silikonöl|Isopropanol|Kontaktspray|WD-40|Reinigungsnadeln",
            ),
        ),
        (("{kind}",),),
        extras="verbrauch",
    ),
    Type(
        "batterie",
        "Akkus & Netzteile",
        "Batterie / Akku",
        "CNS",
        (
            F("kind", "Typ", "AA|AAA|9V Block|CR2032|CR2025|LR44|18650|LiPo"),
            F("brand", "Marke", "Varta|Duracell|Energizer|Basic"),
        ),
        (("{kind}",), ("{brand}",)),
        extras="verbrauch",
    ),
    Type(
        "schleifen",
        "Schleifen & Trennen",
        "Schleifmittel",
        "CNS",
        (
            F("kind", "Art", "Schleifpapier|Schleifvlies|Schleifband|Feile|Polierpaste"),
            F("grit", "Körnung", "80|120|180|240|320|400|600|800|1000|2000"),
        ),
        (("{kind}",), ("K{grit}",)),
        extras="verbrauch",
    ),
    Type(
        "lager",
        "Lager & Führung",
        "Kugellager / Lager",
        "CNS",
        (
            F("kind", "Art", "Kugellager|Linearlager|Flanschlager|Nadellager|Gleitlager"),
            F(
                "size",
                "Maße / Typ",
                "608 (8x22x7)|623 (3x10x4)|625 (5x16x5)|607 (7x19x6)|688 (8x16x4)|LM8UU|LM6UU|LM10UU",
                "mm",
            ),
        ),
        (("{kind}",), ("{size}",)),
        extras="mechanik",
    ),
    Type(
        "kupplung",
        "Antrieb & Bewegung",
        "Wellenkupplung / Riemen",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Wellenkupplung|GT2 Riemen|GT2 Riemenscheibe|Zahnriemen|Spannrolle|Trapezspindel",
            ),
            F("size", "Maße", "5x5|5x8|8x8|6 mm|9 mm|20T|16T", "mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="mechanik",
    ),
    Type(
        "pneumatik",
        "Federn, Dichtungen & Pneumatik",
        "Pneumatik (Fitting, Schlauch, Ventil)",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Steckverbinder gerade|Winkel|T-Stück|Y-Stück|Reduzierstück|Schlauch|Magnetventil|Druckregler|Verteiler",
            ),
            F("dia", "Schlauch-Ø", "4|6|8|10|12", "mm"),
            F("thread", "Gewinde", "M5|G1/8|G1/4|G3/8|G1/2"),
        ),
        (("{kind}",), ("Ø{dia}",), ("{thread}",)),
        extras="mechanik",
    ),
    Type(
        "magnet",
        "Profile & Magnete",
        "Magnet",
        "CNS",
        (
            F("kind", "Art", "Neodym Scheibe|Neodym Quader|Neodym Kugel|Topfmagnet|Ferrit"),
            F("size", "Maße", "5x2|10x3|10x5|20x5|20x10|30x5", "mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="mechanik",
    ),
    Type(
        "profil",
        "Profile & Magnete",
        "Alu-Profil / Verbinder",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Profil 2020|Profil 3030|Winkelverbinder|Nutenstein|Abdeckkappe|Gewindeplatte",
            ),
            F("size", "Länge / Größe", "", hint="z. B. 500 mm, M5, 20x20"),
        ),
        (("{kind}",), ("{size}",)),
        extras="mechanik",
    ),
    Type(
        "schrumpf",
        "Kabel & Leitungen",
        "Schrumpfschlauch",
        "CNS",
        (
            F("dia", "Durchmesser", "1.0-2.0|3.0|4.0|5.0|6.0|8.0|10.0|12.0|20.0", "mm"),
            F("color", "Farbe", "Schwarz|Rot|Blau|Transparent|Gelb"),
        ),
        (("Schrumpfschlauch {dia}",), ("{color}",)),
        extras="elektrik",
    ),
    Type(
        "huelse",
        "Verbinden & Installation",
        "Aderendhülse",
        "CNS",
        (F("size", "Querschnitt", "0.5|0.75|1.0|1.5|2.5|4.0|6.0|Sortiment", "mm²"),),
        (("Aderendhülse {size}",),),
        extras="elektrik",
    ),
    Type(
        "kabelschuh",
        "Verbinden & Installation",
        "Kabelschuh",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Ringkabelschuh|Gabelkabelschuh|Flachstecker|Flachsteckhülse|Stoßverbinder|Rundstecker",
            ),
            F("size", "Querschnitt", "0.5-1.5|1.5-2.5|2.5-4.0|4.0-6.0", "mm²"),
        ),
        (("{kind}",), ("{size}",)),
        extras="elektrik",
    ),
    Type(
        "klemme",
        "Verbinden & Installation",
        "Klemme / Verbinder",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "WAGO 221|WAGO 2273|WAGO 222|Schraubklemme PCB|Lüsterklemme|Kabelclip|Abzweigverbinder",
            ),
            F("poles", "Polzahl", "2|3|4|5|8"),
        ),
        (("{kind}",), ("{poles}-polig",)),
        extras="elektrik",
    ),
    Type(
        "sicherung",
        "Verbinden & Installation",
        "Sicherung",
        "CNS",
        (
            F("kind", "Art", "Glassicherung 5x20|Glassicherung 6.3x32|Flachsicherung|Polyswitch"),
            F("amp", "Strom", "0.5|1|2|3.15|5|10|16", "A"),
        ),
        (("{kind}",), ("{amp}A",)),
        extras="elektrik",
    ),
    Type(
        "mcu",
        "Module & Boards",
        "Mikrocontroller / Board",
        "CMP",
        (
            F(
                "kind",
                "Familie",
                "ESP32|ESP8266 / D1 Mini|Arduino Uno|Arduino Nano|Arduino Pro Mini|Raspberry Pi Pico|Raspberry Pi|STM32|ATtiny|Teensy",
            ),
            F("model", "Modell / Variante", "", hint="z. B. WROOM-32E, S3"),
            F("interface", "Schnittstelle", "USB-C|Micro-USB|UART|I2C|SPI"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "sensor",
        "Module & Boards",
        "Sensor",
        "CMP",
        (
            F(
                "kind",
                "Messgröße",
                "Temperatur / Feuchte|Abstand (Ultraschall)|Abstand (ToF)|Licht|Beschleunigung / Gyro|Druck|Strom / Spannung|Gewicht (HX711)|Hall / Reed|Bewegung (PIR)|Gas|Farbe|GPS|Kamera|Endschalter",
            ),
            F("model", "Modell", "", hint="z. B. DHT22, BME280, MPU6050"),
            F("interface", "Schnittstelle", "I2C|SPI|UART|Analog|Digital|1-Wire"),
        ),
        (("{model}",), ("{kind}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "aktor",
        "Module & Boards",
        "Aktor (Pumpe, Ventil, Summer …)",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Servo|Schrittmotor|Gleichstrommotor|Pumpe|Magnetventil|Lüfter|Buzzer / Lautsprecher|Heizpatrone|Heizmatte|Peltier|Vibrationsmotor",
            ),
            F("model", "Modell / Größe", "", hint="z. B. SG90, NEMA17, 5015"),
            F("voltage", "Spannung", "3.3|5|12|24", "V"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "anzeige",
        "Module & Boards",
        "Anzeige / Display",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "LCD 16x2|LCD 20x4|OLED 0.96|OLED 1.3|7-Segment (TM1637)|TFT|E-Paper|LED-Matrix|Touch-Display",
            ),
            F("interface", "Schnittstelle", "I2C|SPI|UART|Parallel"),
        ),
        (("{kind}",),),
        True,
        extras="elektronik",
    ),
    Type(
        "schalter",
        "Bauteile",
        "Schalter / Taster / Eingabe",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Taster|Kippschalter|Wippschalter|Drehgeber (Encoder)|Joystick|Potentiometer|Reed-Kontakt|Endschalter|DIP-Schalter|Tastkappe",
            ),
            F("model", "Variante", "", hint="z. B. 6x6, KY-040"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "treiber",
        "Module & Boards",
        "Relais / MOSFET / Treiber",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Relais-Modul|MOSFET-Modul|Motortreiber|H-Brücke|Solid-State-Relais|Level-Shifter|Dimmer-Modul",
            ),
            F("model", "Modell", "", hint="z. B. A4988, TMC2209, IRF520"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "strom",
        "Module & Boards",
        "Stromversorgung / Wandler",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Step-Down (Buck)|Step-Up (Boost)|Ladeplatine (TP4056)|Netzteil-Modul|Spannungsregler|USB-C PD Trigger|Batteriehalter|Powerbank-Modul",
            ),
            F("model", "Modell", "", hint="z. B. LM2596, XL4015"),
            F("voltage", "Ausgang", "3.3|5|9|12|24", "V"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "funk",
        "Module & Boards",
        "Funk / Kommunikation",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Bluetooth|WLAN-Modul|LoRa|nRF24|RFID / NFC|Infrarot|433 MHz|CAN|RS485|GSM",
            ),
            F("model", "Modell", "", hint="z. B. RC522, HC-05"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "led",
        "Bauteile",
        "LED / Licht",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "LED 5mm|LED 3mm|RGB-LED|LED-Streifen|WS2812 (NeoPixel)|LED-Ring|Laserdiode|IR-LED|Power-LED",
            ),
            F("color", "Farbe", "Rot|Grün|Blau|Gelb|Weiß|Warmweiß|RGB"),
        ),
        (("{kind}",), ("{color}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "passiv",
        "Bauteile",
        "Widerstand / Kondensator / Spule",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Widerstand|Elko|Keramikkondensator|Folienkondensator|Spule|Potentiometer|Thermistor|Varistor",
            ),
            F(
                "value",
                "Wert",
                "10R|47R|100R|220R|330R|470R|1k|2.2k|4.7k|10k|47k|100k|1M|100nF|10uF|100uF|470uF",
            ),
            F("package", "Bauform", "THT 1/4W|SMD 0805|SMD 0603|Radial|Axial"),
        ),
        (("{kind}",), ("{value}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "halbleiter",
        "Bauteile",
        "Transistor / Diode / IC",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Transistor|MOSFET|Diode|Z-Diode|Gleichrichter|Optokoppler|Operationsverstärker|Logik-IC|Spannungsregler-IC|Timer (555)",
            ),
            F("model", "Typ", "", hint="z. B. BC547, IRLZ44N, 1N4148, LM7805"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "stecker",
        "Prototyping & Gehäuse",
        "Stecker / Buchse / Header",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "GX12|GX16|DC-Hohlstecker|DC-Buchse|Pin-Header|JST|XT60|XT30|Dupont|USB-Buchse|Klinke|SMA|Schraubklemme|Molex",
            ),
            F("pins", "Polzahl", "2|3|4|5|6|8|10|40"),
        ),
        (("{kind}",), ("{pins}-polig",)),
        True,
        extras="elektronik",
    ),
    Type(
        "proto",
        "Prototyping & Gehäuse",
        "Platine / Prototyping / Kabel",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Lochrasterplatine|Breadboard|Jumper-Kabel|Dupont-Kabel|Abstandsbolzen|Terminal Adapter|Servokabel|Silikonlitze",
            ),
            F("size", "Größe / Länge", "", hint="z. B. 5x7 cm, 20 cm, M3x10"),
        ),
        (("{kind}",), ("{size}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "smarthome",
        "Module & Boards",
        "Smart-Home-Modul",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "WLAN-Dimmer|Schaltaktor|Thermostat|Tür-/Fenstersensor|LED-Controller|Zigbee-Gateway|Steckdose|Taster",
            ),
            F("brand", "Marke", "Moes|Tuya|Shelly|Sonoff|IKEA"),
        ),
        (("{brand}",), ("{kind}",)),
        True,
        extras="elektronik",
    ),
    Type(
        "zange",
        "Handwerkzeug",
        "Zange / Schneider",
        "TOL",
        (
            F(
                "kind",
                "Art",
                "Seitenschneider|Flachzange|Spitzzange|Abisolierzange|Crimpzange|Wasserpumpenzange|Pinzette|Elektronik-Schneider",
            ),
            F("brand", "Marke", "Xuron|Knipex|Wera|Wiha|Bosch"),
        ),
        (("{kind}",), ("{brand}",)),
        extras="werkzeug",
    ),
    Type(
        "schrauber",
        "Handwerkzeug",
        "Schraubendreher / Bits / Schlüssel",
        "TOL",
        (
            F(
                "kind",
                "Art",
                "Schraubendreher|Bit-Satz|Innensechskant-Satz|Torx-Satz|Steckschlüssel|Gabelschlüssel|Hakenschlüssel|Präzisionsschraubendreher",
            ),
            F("size", "Größe", "", hint="z. B. 2.5 mm, PH2, 10 mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="werkzeug",
    ),
    Type(
        "bohrer",
        "Bohren, Fräsen & Sägen",
        "Bohrer / Gewinde / Senker",
        "TOL",
        (
            F(
                "kind",
                "Art",
                "Spiralbohrer HSS|Holzbohrer|Steinbohrer|Stufenbohrer|Kegelsenker|Gewindebohrer|Schneideisen|Forstnerbohrer|Fräser|Bohrfutter",
            ),
            F("size", "Maß", "", hint="z. B. 3.2 mm, M4, 4-12 mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="werkzeug",
    ),
    Type(
        "messen",
        "Messen & Sets",
        "Messen / Anreißen",
        "TOL",
        (
            F(
                "kind",
                "Art",
                "Messschieber|Wasserwaage|Maßband|Winkel|Multimeter|Anreißnadel|Bleistift|Markierstift|Lineal",
            ),
            F("size", "Variante", "", hint="z. B. 150 mm, 5 m"),
        ),
        (("{kind}",), ("{size}",)),
        extras="werkzeug",
    ),
    Type(
        "schneiden",
        "Handwerkzeug",
        "Schneiden / Feilen / Entgraten",
        "TOL",
        (
            F(
                "kind",
                "Art",
                "Cuttermesser|Skalpell|Entgrater|Feile|Raspel|Säge|Schaber (3D-Druck)|Spachtel|Schere",
            ),
            F("size", "Variante", ""),
        ),
        (("{kind}",), ("{size}",)),
        extras="werkzeug",
    ),
    Type(
        "werkzeug_sonst",
        "Handwerkzeug",
        "Anderes Werkzeug",
        "TOL",
        (
            F(
                "kind",
                "Bezeichnung",
                "Lötkolben|Heißklebepistole|Hammer|Zwinge|Schraubstock|Bohrmaschine|Akkuschrauber|Schleifer|Heißluftpistole",
            ),
            F("brand", "Marke", "Makita|Bosch|Wera|Hobby Zone"),
        ),
        (("{kind}",), ("{brand}",)),
        extras="werkzeug",
    ),
    Type(
        "duese",
        "Druckerteile",
        "Düse / Hotend",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Düse Messing|Düse gehärtet|Düse Edelstahl|Heizblock|Hotend komplett|Heizpatrone|Thermistor|Silikonsocke|Kühlkörper",
            ),
            F("size", "Größe", "0.2|0.4|0.6|0.8", "mm"),
            F("model", "Passend für", "MK8|V6|Volcano|Bambu|Creality|Prusa"),
        ),
        (("{kind}",), ("{size}mm",), ("{model}",)),
        True,
        extras="drucker",
    ),
    Type(
        "druckerteil",
        "Druckerteile",
        "Druckerteil",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Druckplatte|Lüfter|Schrittmotor|PTFE-Schlauch|Endstop|Extruder-Zahnrad|Spannrolle|Netzteil|Mainboard|Gewindespindel|Kupplung",
            ),
            F("model", "Passend für / Maß", "", hint="z. B. NEMA17, 4010, Ender 3"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="drucker",
    ),
    Type(
        "netzteil",
        "Akkus & Netzteile",
        "Netzteil",
        "CMP",
        (
            F("kind", "Art", "Netzteil|Steckernetzteil|Schaltnetzteil|Labornetzteil|Ladegerät"),
            F("volt", "Spannung", "5|9|12|19|24|48", "V"),
            F("amp", "Strom", "0.5|1|2|3|5|10|15|20", "A"),
            F(
                "plug",
                "Stecker (Ausgang)",
                "DC 5,5x2,1|DC 5,5x2,5|DC 3,5x1,35|USB-C|Schraubklemmen|XT60",
            ),
            F("model", "Passend für", "", hint="z. B. Ender 3, Bambu, LED-Streifen"),
        ),
        (("{kind}",), ("{volt}V",), ("{amp}A",), ("{plug}",), ("{model}",)),
        True,
        extras="drucker",
    ),
    Type(
        "laser",
        "Laser",
        "Laser-Zubehör",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Laserlinse|Spiegel|Luftpumpe|Luftdüse|Wabenbett|Laserdiode|Treiber|Schutzbrille|Not-Aus",
            ),
            F("model", "Variante", "", hint="z. B. 5 W, 450 nm"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="drucker",
    ),
    Type(
        "etiketten",
        "Ordnung & Etiketten",
        "Etikettenrolle / Druckzubehör",
        "CNS",
        (
            F(
                "kind",
                "Art",
                "Etikettenrolle D30|Etikettenrolle|Druckfolie|Thermopapier|Wärmeleitpad",
            ),
            F("size", "Größe", "12x40 mm|14x30 mm|15x30 mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="drucker",
    ),
    Type(
        "netzwerkkabel",
        "Netzwerk",
        "Netzwerkkabel (Patchkabel)",
        "CMP",
        (
            F("kind", "Kategorie", "Cat5e|Cat6|Cat6a|Cat7|Cat8|Koax|LWL"),
            F("length", "Länge", "0.25|0.5|1|2|3|5|10|15|20|25|50", "m"),
            F("color", "Farbe", "Grau|Blau|Gelb|Rot|Grün|Schwarz|Weiß|Orange"),
            F("shield", "Schirmung", "UTP|F/UTP|S/FTP"),
        ),
        (("Netzwerkkabel",), ("{kind}",), ("{length}m",), ("{color}",)),
        extras="netzwerk",
    ),
    Type(
        "rj45",
        "Netzwerk",
        "RJ45 / Keystone / Dose",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "RJ45-Stecker|Keystone|Netzwerkdose|Kupplung|Tülle|Crimpzange|Patchpanel|Winkeladapter",
            ),
            F("cat", "Kategorie", "Cat5e|Cat6|Cat6a|Cat7"),
        ),
        (("{kind}",), ("{cat}",)),
        extras="netzwerk",
    ),
    Type(
        "netzwerkgeraet",
        "Netzwerk",
        "Netzwerkgerät (Switch, Router, Adapter)",
        "CMP",
        (
            F(
                "kind",
                "Art",
                "Switch|Router|Access Point|Powerline|Medienkonverter|USB-LAN-Adapter|PoE-Injektor|PoE-Splitter",
            ),
            F("model", "Modell / Ports", "", hint="z. B. 8 Port Gigabit"),
        ),
        (("{kind}",), ("{model}",)),
        True,
        extras="netzwerk",
    ),
    Type(
        "holz",
        "Holz, Metall & Kunststoff",
        "Holz / Platte",
        "RAW",
        (
            F(
                "kind",
                "Art",
                "Kiefer|Fichte|Buche|Eiche|MDF|Pappel-Sperrholz|Multiplex|Dachlatte|Rundholz|Leiste",
            ),
            F("size", "Maße", "", hint="z. B. 3 mm, 20x40x1000"),
        ),
        (("{kind}",), ("{size}",)),
        extras="material",
    ),
    Type(
        "metall",
        "Holz, Metall & Kunststoff",
        "Metall / Kunststoff",
        "RAW",
        (
            F("kind", "Art", "Aluminium|Stahl|Edelstahl|Messing|Kupfer|Acryl|PVC|POM|Polycarbonat"),
            F("form", "Form", "Blech|Flachprofil|Winkelprofil|Rohr|Rundstab|Vierkant|Platte"),
            F("size", "Maße", "", hint="z. B. 2 mm, 20x2, Ø8"),
        ),
        (("{kind}",), ("{form}",), ("{size}",)),
        extras="material",
    ),
    Type(
        "kabel",
        "Kabel & Leitungen",
        "Kabel (USB, Strom, Audio, Meterware)",
        "ART",
        (
            F(
                "kind",
                "Art",
                "USB-Kabel|Stromkabel|Verlängerung|HDMI|Audio|Lautsprecher|Litze|Meterware",
            ),
            F("ends", "Stecker", "", hint="z. B. USB-C auf USB-A"),
            F("length", "Länge", "0.5|1|2|3|5|10", "m"),
        ),
        (("{kind}",), ("{ends}",), ("{length}m",)),
        extras="elektrik",
    ),
    Type(
        "gridfinity",
        "Ordnung & Etiketten",
        "Gridfinity (Bin / Baseplate)",
        "ART",
        (
            F("kind", "Art", "Bin|Baseplate|Deckel|Teiler|Magnet-Einsatz|Eckverbinder"),
            F("size", "Raster", "1x1|2x1|2x2|3x2|3x3|4x2|4x3|4x4", hint="Zellen, z. B. 2x1"),
            F("height", "Höhe", "3u|4u|5u|6u|7u|9u", hint="Einheiten à 7 mm"),
            F("color", "Farbe", "Schwarz|Weiß|Grau|Rot|Blau|Grün|Orange|Gelb"),
        ),
        (("Gridfinity {kind}",), ("{size}",), ("{height}",), ("{color}",)),
        extras="drucker",
    ),
    Type(
        "bohrersatz",
        "Messen & Sets",
        "Set / Sortiment (ein Etikett für viele)",
        "ART",
        (
            F("kind", "Art", "Bohrersatz|Bitset|Schlüsselsatz|Feilensatz|Sortiment|Kabelset"),
            F("detail", "Inhalt", "", hint="z. B. 1–10 mm, 25 Teile"),
            F("brand", "Hersteller"),
        ),
        (("{kind}",), ("{detail}",), ("{brand}",)),
        extras="werkzeug",
    ),
    Type(
        "heissleim",
        "Kleben & Dichten",
        "Heißkleber / Epoxid / Dichtmasse",
        "ART",
        (
            F(
                "kind",
                "Art",
                "Heißklebesticks|2K-Epoxid|Silikon|Acryl|Sekundenkleber|Montagekleber",
            ),
            F("size", "Größe", "", hint="z. B. 11 mm, 25 ml"),
        ),
        (("{kind}",), ("{size}",)),
        extras="verbrauch",
    ),
    Type(
        "farbe",
        "Farbe & Oberfläche",
        "Farbe / Lack / Spray",
        "ART",
        (
            F("kind", "Art", "Sprühlack|Acrylfarbe|Primer|Klarlack|Beize|Öl|Lasur"),
            F("color", "Farbe"),
            F("size", "Menge", "", hint="z. B. 400 ml"),
        ),
        (("{kind}",), ("{color}",), ("{size}",)),
        extras="verbrauch",
    ),
    Type(
        "kabelbinder",
        "Kabel & Leitungen",
        "Kabelbinder / Kabelkanal / Schlauch",
        "ART",
        (
            F(
                "kind",
                "Art",
                "Kabelbinder|Klettband|Kabelkanal|Wellrohr|Spiralschlauch|Zugentlastung",
            ),
            F("size", "Maße", "", hint="z. B. 200x3,6 mm"),
            F("color", "Farbe", "Schwarz|Weiß|Natur|Rot|Blau"),
        ),
        (("{kind}",), ("{size}",), ("{color}",)),
        extras="elektrik",
    ),
    Type(
        "akku",
        "Akkus & Netzteile",
        "Akku / Ladegerät / Powerbank",
        "ART",
        (
            F("kind", "Art", "LiPo|Li-Ion 18650|NiMH|Bleigel|Powerbank|Ladegerät|BMS"),
            F("cap", "Kapazität", "", hint="z. B. 2000 mAh"),
            F("volt", "Spannung", "3.7V|7.4V|11.1V|12V|24V"),
        ),
        (("{kind}",), ("{cap}",), ("{volt}",)),
        extras="elektronik",
    ),
    Type(
        "gehaeuse",
        "Prototyping & Gehäuse",
        "Gehäuse / Halter / Montage",
        "ART",
        (
            F(
                "kind",
                "Art",
                "Gehäuse|Hutschienen-Gehäuse|Abstandshalter|Platinenhalter|Lüfter|Kühlkörper",
            ),
            F("size", "Maße", "", hint="z. B. 80x60x30"),
        ),
        (("{kind}",), ("{size}",)),
        extras="elektronik",
    ),
    Type(
        "buero",
        "Haushalt, Licht & Sonstiges",
        "Büro / Haushalt / Sonstiges Verbrauch",
        "ART",
        (F("name", "Bezeichnung", "", hint="z. B. Handschuhe, Isolierband"),),
        (("{name}",),),
        extras="verbrauch",
    ),
    Type(
        "allgemein",
        "Haushalt, Licht & Sonstiges",
        "Sonstiges (freier Name)",
        "ART",
        (F("name", "Bezeichnung", "", hint="z. B. Zahnrad 20 Zähne"),),
        (("{name}",),),
        extras="material",
    ),
    Type(
        "filament",
        "Filament & Harz",
        "Filament-Spule",
        "FIL",
        (
            F("brand", "Hersteller", "Prusament|eSun|Sunlu|Bambu Lab|Creality|Polymaker|Elegoo"),
            F("plastic", "Kunststoff", "PLA|PLA+|PETG|ABS|ASA|TPU|PA6|PA12|PC|PVA|PP", row="werk"),
            F(
                "additive",
                "Zusatz",
                "Glasfaser|Carbonfaser|Kevlar|Holz|Metall|Glitzer|Marmor",
                row="werk",
            ),
            F(
                "additive_pct",
                "Anteil",
                "5|10|15|20|25|30",
                "%",
                hint="Kunststoff = 100 − Zusatz",
                row="werk",
            ),
            F("color", "Farbe", "Schwarz|Weiß|Grau|Rot|Blau|Grün|Gelb|Orange|Transparent|Natur"),
            F("diameter", "Durchmesser", "1.75|2.85", "mm", row="maß"),
            F("weight", "Gewicht je Spule", "0.25|0.5|0.75|1|2|3", "kg", row="maß"),
            F(
                "spool_type",
                "Spulentyp",
                "Pappe|Plastik|Mehrweg|Masterspool|Refill (ohne Spule)|Metall",
                row="spule",
            ),
            F("spool_weight", "Spulenleergewicht", "150|200|250|300", "g", row="spule"),
            F("price", "Preis je Spule", "", "€", row="spule"),
        ),
        (("{brand}",), ("{material}",), ("{color}",)),
        material="fil",
        single=True,
        extras="basis",
    ),
    Type(
        "harz",
        "Filament & Harz",
        "UV-Harz-Flasche",
        "RES",
        (
            F("brand", "Hersteller", "Elegoo|Anycubic|Siraya Tech|Phrozen|Formlabs"),
            F(
                "material",
                "Harztyp",
                "Standard|ABS-like|Tough|Flexibel|Wasserwaschbar|Hochtemperatur",
            ),
            F("color", "Farbe", "Grau|Schwarz|Weiß|Transparent|Klar|Rot|Blau|Grün"),
            F(
                "volume",
                "Inhalt je Flasche",
                "250|500|1000",
                "ml",
                hint="250 ml · 500 ml · 1 l",
                row="fl",
            ),
            F("bottle_weight", "Leerflasche", "", "g", row="fl"),
            F("price", "Preis je Flasche", "", "€", row="fl"),
        ),
        (("{brand}",), ("{material}",), ("{color}",), ("{volume}ml",)),
        material="res",
        single=True,
        extras="basis",
    ),
    Type(
        "steckernetzteil",
        "Akkus & Netzteile",
        "Steckernetzteil (mit Eingang)",
        "PSU",
        (
            F("volt", "Spannung", "3.3|5|9|12|19|24|48", "V"),
            F("amp", "Strom", "0.5|1|2|3|5|10", "A"),
            F("plug", "Stecker (Ausgang)", "DC 5,5x2,1|DC 5,5x2,5|DC 3,5x1,35|USB-C|USB-A|Klemmen"),
            F("input", "Eingang", "230 V Kaltgerät|230 V Euro-Stecker|12 V|24 V"),
        ),
        (("Netzteil",), ("{volt}V",), ("{amp}A",), ("{plug}",)),
        material="psu",
        extras="elektrik",
    ),
    Type(
        "kabel_stecker",
        "Kabel & Leitungen",
        "Kabel mit Steckern (Länge, Stecker A/B)",
        "CBL",
        (
            F("plug_a", "Stecker A", "USB-A|USB-C|Micro-USB|HDMI|DC 5,5x2,1|JST-XH|Dupont|RJ45"),
            F("plug_b", "Stecker B", "USB-A|USB-C|Micro-USB|HDMI|DC 5,5x2,1|JST-XH|Dupont|RJ45"),
            F("length", "Länge", "0.2|0.5|1|2|3|5|10", "m"),
        ),
        (("Kabel",), ("{plug_a}",), ("{plug_b}",), ("{length}m",)),
        material="cbl",
        extras="elektrik",
    ),
    Type(
        "werkzeug_allg",
        "Handwerkzeug",
        "Werkzeug (allgemein)",
        "TOL",
        (
            F("kind", "Art", "Zange|Schraubendreher|Schlüssel|Feile|Säge|Messer|Bohrer|Messgerät"),
            F("brand", "Hersteller", "Wera|Wiha|Knipex|Bosch|Makita|Würth|Stanley"),
            F("size", "Größe / Maß", "", hint="z. B. 3 mm, PH2"),
        ),
        (("{kind}",), ("{brand}",), ("{size}",)),
        extras="werkzeug",
    ),
    Type(
        "ppe",
        "Schutzausrüstung",
        "Schutzausrüstung (PPE)",
        "PPE",
        (
            F(
                "kind",
                "Art",
                "Handschuhe|Schutzbrille|Atemschutz FFP2|Gehörschutz|Schürze|Laserschutzbrille",
            ),
            F("size", "Größe", "S|M|L|XL"),
            F("material", "Material", "Nitril|Latex|Leder|Stoff"),
        ),
        (("{kind}",), ("{size}",), ("{material}",)),
        extras="basis",
    ),
    Type(
        "norb16_bin",
        "Ordnung & Etiketten",
        "Norb16-Bin (3D-Druck)",
        "ART",
        (
            F("size", "Größe", "1x1|2x1|2x2|3x1|4x1"),
            F("state", "Zustand", "nicht gedruckt|gedruckt"),
        ),
        (("Norb16 Bin",), ("{size}",), ("({state})",)),
        extras="drucker",
    ),
)

# Seit 2.0: weitere Werkstatt-Typen. Sie stehen hinter den bisherigen, damit `guess` bei
# Gleichstand weiterhin die bisherigen Typen bevorzugt.
# fmt: off
TYPES_2_0: tuple[Type, ...] = (
    # Befestigung
    Type(
        "niete", "Dübel, Nieten & Stifte", "Niete / Einnietmutter", "CNS",
        (
            F("kind", "Art", "Blindniete|Popniete|Hohlniete|Vollniete|Einnietmutter|Spreizniete"),
            F("dia", "Durchmesser / Gewinde", "2.4|3|3.2|4|4.8|5|6|M3|M4|M5|M6|M8", "mm"),
            F("length", "Länge", "6|8|10|12|14|16|20|25", "mm"),
            F("material", "Material", "Aluminium|Stahl|Edelstahl|Kupfer|Kunststoff"),
        ),
        (("{kind}",), ("{dia}x{length}", "{dia}")),
        extras="kleinteile",
    ),
    Type(
        "sicherungsring", "Dübel, Nieten & Stifte", "Sicherungsring / Splint / Stift", "CNS",
        (
            F("kind", "Art", "Sicherungsring Welle (DIN 471)|Sicherungsring Bohrung (DIN 472)|"
              "Sicherungsscheibe (DIN 6799)|Splint|Federstecker|Klappstecker|Zylinderstift|"
              "Spannstift|Kegelstift"),
            F("size", "Größe (Welle / Ø)", "2|3|4|5|6|8|10|12|15|20|25", "mm"),
            F("length", "Länge (Stifte)", "10|16|20|30|40|50", "mm"),
            F("material", "Material", "Federstahl|Edelstahl|Stahl verzinkt"),
        ),
        (("{kind}",), ("{size}x{length}", "{size}mm")),
        extras="kleinteile",
    ),
    Type(
        "schelle", "Schellen, Haken & Beschläge", "Schlauch- / Rohrschelle", "CNS",
        (
            F("kind", "Art", "Schlauchschelle|Ohrklemme|Federbandschelle|Rohrschelle|Kabelschelle|"
              "P-Clip|Gelenkbolzenschelle|Rohrhalter"),
            F("range", "Spannbereich / Ø", "6-12|8-16|10-16|12-22|16-27|20-32|25-40|32-50", "mm"),
            F("width", "Bandbreite", "6|9|12", "mm", extra=True),
            F("material", "Material", "Stahl verzinkt|Edelstahl W4|Kunststoff|Gummi"),
        ),
        (("{kind}",), ("{range}mm",)),
        extras="kleinteile",
    ),
    Type(
        "haken", "Schellen, Haken & Beschläge", "Haken / Öse / Karabiner", "CNS",
        (
            F("kind", "Art", "Schraubhaken|Ringschraube|Augenschraube|Ringmutter|S-Haken|Wandhaken|"
              "Karabiner|Schäkel|Seilklemme|Spannschloss"),
            F("size", "Größe / Gewinde", "M4|M5|M6|M8|M10|30|40|50|60|80", hint="Gewinde oder Länge in mm"),
            F("material", "Material", "Stahl verzinkt|Edelstahl|Messing"),
        ),
        (("{kind}",), ("{size}",)),
        extras="kleinteile",
    ),
    Type(
        "beschlag", "Schellen, Haken & Beschläge", "Scharnier / Beschlag / Winkel", "CNS",
        (
            F("kind", "Art", "Scharnier|Klavierband|Topfband|Winkel|Flachverbinder|Lochband|"
              "Möbelverbinder|Schubladenauszug|Griff|Riegel|Magnetschnäpper"),
            F("size", "Größe", "20|25|30|40|50|60|80|100|150", "mm"),
            F("material", "Material", "Stahl verzinkt|Edelstahl|Messing|Aluminium|Kunststoff"),
        ),
        (("{kind}",), ("{size}mm",)),
        extras="kleinteile",
    ),
    # Mechanik & Antrieb
    Type(
        "dichtung", "Federn, Dichtungen & Pneumatik", "O-Ring / Dichtung", "CNS",
        (
            F("kind", "Art", "O-Ring|Flachdichtung|Dichtring Kupfer|Dichtring Aluminium|"
              "Wellendichtring|Gummitülle|Quad-Ring|O-Ring-Sortiment"),
            F("id", "Innen-Ø", "3|4|5|6|8|10|12|15|20|25|30", "mm", row="ring"),
            F("cs", "Schnurstärke / Dicke", "1|1.5|1.9|2|2.5|3|3.5|4", "mm", row="ring"),
            F("material", "Material", "NBR|FKM (Viton)|EPDM|Silikon|PTFE|Kupfer|Fiber"),
        ),
        (("{kind}",), ("{id}x{cs}", "Ø{id}"), ("{material}",)),
        label_lines=("{kind} {id}x{cs}", "{material}"),
        extras="mechanik",
    ),
    Type(
        "feder", "Federn, Dichtungen & Pneumatik", "Feder", "CNS",
        (
            F("kind", "Art", "Druckfeder|Zugfeder|Schenkelfeder|Tellerfeder|Gasdruckfeder|Federsortiment"),
            F("od", "Außen-Ø", "3|4|5|6|8|10|12|15|20", "mm", row="dim"),
            F("length", "Länge", "5|10|15|20|25|30|40|50", "mm", row="dim"),
            F("wire", "Drahtstärke", "0.3|0.5|0.6|0.8|1|1.2|1.5|2", "mm", extra=True),
            F("force", "Kraft (Gasfeder)", "50|100|150|200|300|500", "N", extra=True),
        ),
        (("{kind}",), ("Ø{od}",), ("L{length}",)),
        extras="mechanik",
    ),
    Type(
        "zahnriemen", "Antrieb & Bewegung", "Zahnriemen", "CNS",
        (
            F("profile", "Profil", "GT2|GT3|HTD 3M|HTD 5M|T2.5|T5|XL"),
            F("width", "Breite", "6|9|10|12|15|20", "mm"),
            F("kind", "Ausführung", "Meterware (offen)|Geschlossen|Mit Stahlcord|Mit Glasfaser"),
            F("length", "Länge (geschlossen)", "110|158|200|280|400|610|852", "mm"),
        ),
        (("Zahnriemen {profile}",), ("{width}mm",), ("L{length}",)),
        extras="mechanik",
    ),
    Type(
        "riemenscheibe", "Antrieb & Bewegung", "Riemenscheibe / Umlenkrolle", "CNS",
        (
            F("kind", "Art", "Zahnriemenscheibe|Umlenkrolle gezahnt|Umlenkrolle glatt|Spannrolle|Keilriemenscheibe"),
            F("profile", "Profil", "GT2|GT3|HTD 3M|HTD 5M|T5"),
            F("teeth", "Zähne", "16|20|30|36|40|60", row="dim"),
            F("bore", "Bohrung", "3|5|6|6.35|8|10", "mm", row="dim"),
            F("width", "Für Riemenbreite", "6|9|10|15", "mm", extra=True),
        ),
        (("{kind}",), ("{profile}",), ("{teeth}Z",), ("B{bore}",)),
        extras="mechanik",
    ),
    Type(
        "zahnrad", "Antrieb & Bewegung", "Zahnrad / Zahnstange / Getriebe", "CNS",
        (
            F("kind", "Art", "Stirnrad|Kegelrad|Schnecke|Schneckenrad|Zahnstange|Planetengetriebe|Getriebemotor-Zahnrad"),
            F("module", "Modul", "0.5|0.8|1|1.5|2|2.5"),
            F("teeth", "Zähne", "10|12|15|20|25|30|40|50|60", row="dim"),
            F("bore", "Bohrung", "3|4|5|6|8|10|12", "mm", row="dim"),
            F("material", "Material", "Stahl|Messing|POM|Nylon|Kunststoff"),
        ),
        (("{kind}",), ("M{module}",), ("{teeth}Z",)),
        extras="mechanik",
    ),
    Type(
        "linear", "Lager & Führung", "Linearführung / Welle", "CNS",
        (
            F("kind", "Art", "Linearwelle|Linearschiene|Führungswagen|Linearkugellager|Wellenhalter|"
              "Wellenbock|V-Slot-Rolle|Linearmodul"),
            F("size", "Ø / Baugröße", "6|8|10|12|16|20|MGN7|MGN9|MGN12|MGN15|LM8UU|SK8|SHF8"),
            F("length", "Länge", "100|200|300|400|500|600|1000", "mm"),
        ),
        (("{kind}",), ("{size}x{length}", "{size}")),
        extras="mechanik",
    ),
    Type(
        "gleitlager", "Lager & Führung", "Gleitlager / Buchse / Distanzhülse", "CNS",
        (
            F("kind", "Art", "Gleitlager Sinterbronze|Gleitlager Kunststoff (igus)|Flanschbuchse|"
              "Messingbuchse|Distanzhülse|Distanzrolle|Anlaufscheibe"),
            F("id", "Innen-Ø", "3|4|5|6|8|10|12|16", "mm", row="dim"),
            F("od", "Außen-Ø", "5|6|8|10|12|14|16|20", "mm", row="dim"),
            F("length", "Länge", "3|4|5|6|8|10|12|16|20", "mm", row="dim"),
        ),
        (("{kind}",), ("{id}x{od}x{length}", "{id}x{od}", "Ø{id}")),
        extras="mechanik",
    ),
    Type(
        "spindel", "Lager & Führung", "Gewindespindel / Trapezmutter", "CNS",
        (
            F("kind", "Art", "Trapezgewindespindel|Trapezmutter|Anti-Backlash-Mutter|"
              "Kugelumlaufspindel|Kugelumlaufmutter|Spindel mit Schrittmotor"),
            F("size", "Gewinde", "Tr8x2|Tr8x4|Tr8x8|Tr10x2|Tr12x3|Tr16x4|SFU1204|SFU1605|SFU1610"),
            F("length", "Länge", "100|200|300|400|500|600|1000", "mm"),
            F("material", "Material", "Edelstahl|Stahl|Messing|POM|Bronze"),
        ),
        (("{kind}",), ("{size}",), ("{length}mm",)),
        extras="mechanik",
    ),
    Type(
        "rolle", "Lager & Führung", "Rolle / Rad / Gleiter", "CNS",
        (
            F("kind", "Art", "Lenkrolle|Lenkrolle mit Bremse|Bockrolle|Kugelrolle|Möbelrolle|Rad|"
              "Laufrolle|Schwerlastrolle|Möbelgleiter"),
            F("dia", "Rad-Ø", "25|30|40|50|75|100|125|160", "mm"),
            F("mount", "Befestigung", "Anschraubplatte|Gewindezapfen|Steckzapfen|Achse|Kleben"),
            F("load", "Tragkraft", "20|30|50|75|100|150|250", "kg"),
        ),
        (("{kind}",), ("Ø{dia}",)),
        extras="mechanik",
    ),
    Type(
        "motor", "Antrieb & Bewegung", "Motor / Servo (Schritt, DC, BLDC)", "CMP",
        (
            F("kind", "Art", "Schrittmotor|Schrittmotor NEMA17|Schrittmotor NEMA14|Schrittmotor NEMA23|"
              "Schrittmotor 28BYJ-48|Gleichstrommotor|Getriebemotor|Servo SG90|Servo MG996R|"
              "Brushless|Vibrationsmotor"),
            F("voltage", "Spannung", "3.3|5|6|12|24|48", "V"),
            F("current", "Strom", "0.5|1|1.5|2|2.5|3", "A", extra=True),
            F("model", "Modell / Typ", hint="z. B. 17HS4401, LDO-42STH40"),
        ),
        (("{kind}",), ("{model}",), ("{voltage}V",)),
        cmp=True,
        extras="basis",
    ),
    Type(
        "luefter", "Antrieb & Bewegung", "Lüfter", "CMP",
        (
            F("size", "Baugröße", "2510|3010|4010|4020|5015|6015|6025|8025|9225|12025|14025"),
            F("voltage", "Spannung", "5|12|24", "V"),
            F("kind", "Bauart", "Axial|Radial (Blower)|Querstrom"),
            F("plug", "Anschluss", "2-Pin|3-Pin|4-Pin PWM|JST-XH|USB", extra=True),
            F("bearing", "Lager", "Gleitlager|Kugellager|Hydraulik", extra=True),
        ),
        (("Lüfter",), ("{size}",), ("{voltage}V",), ("{kind}",)),
        cmp=True,
        extras="basis",
    ),
    # Elektronik
    Type(
        "relais", "Bauteile", "Relais", "CMP",
        (
            F("kind", "Art", "Printrelais|Hutschienenrelais|Kfz-Relais|Reed-Relais|Solid-State-Relais|Zeitrelais|Stromstoßschalter"),
            F("voltage", "Spulenspannung", "3|5|12|24|230", "V"),
            F("contacts", "Kontakte", "1 Schließer|1 Wechsler|2 Wechsler|4 Wechsler"),
            F("current", "Schaltstrom", "1|2|5|10|16|30|40", "A"),
            F("model", "Modell", hint="z. B. SRD-05VDC-SL-C", extra=True),
        ),
        (("{kind}",), ("{voltage}V",), ("{contacts}",)),
        cmp=True,
        extras="elektronik",
    ),
    Type(
        "quarz", "Bauteile", "Quarz / Oszillator", "CMP",
        (
            F("kind", "Art", "Quarz|Quarzoszillator|Keramikresonator|Uhrenquarz|MEMS-Oszillator"),
            F("frequency", "Frequenz", "32.768 kHz|4 MHz|8 MHz|12 MHz|16 MHz|20 MHz|25 MHz|27 MHz"),
            F("package", "Bauform", "HC-49|HC-49S|SMD 3225|SMD 5032|DIP-4|SOP-4"),
        ),
        (("{kind}",), ("{frequency}",), ("{package}",)),
        cmp=True,
        extras="elektronik",
    ),
    Type(
        "kuehlkoerper", "Prototyping & Gehäuse", "Kühlkörper / Wärmeleitmaterial", "CMP",
        (
            F("kind", "Art", "Kühlkörper|Kühlkörper TO-220|Kühlkörper Raspberry Pi|Wärmeleitpad|"
              "Wärmeleitpaste|Wärmeleitkleber|Isolierscheibe|Heatpipe"),
            F("size", "Größe", "9x9|14x14|20x20|40x40|60x60|100x100", "mm"),
            F("thickness", "Dicke / Höhe", "0.5|1|1.5|2|3|5|10|20", "mm"),
            F("conductivity", "Wärmeleitfähigkeit", "1.5|3|6|8|12", "W/mK", extra=True),
        ),
        (("{kind}",), ("{size}",), ("{thickness}mm",)),
        extras="drucker",
    ),
    # Netzwerk & IT
    Type(
        "speicher", "Computer & Speicher", "Speicherkarte / USB-Stick / SSD", "CMP",
        (
            F("kind", "Art", "microSD|SD-Karte|USB-Stick|SSD SATA|SSD NVMe|HDD 2.5|HDD 3.5|eMMC-Modul"),
            F("capacity", "Kapazität", "4|8|16|32|64|128|256|512|1000|2000|4000", "GB"),
            F("speed", "Klasse / Standard", "Class 10|U1|U3|A1|A2|USB 2.0|USB 3.0|SATA III|PCIe 3.0|PCIe 4.0"),
        ),
        (("{kind}",), ("{capacity}GB",), ("{speed}",)),
        extras="netzwerk",
    ),
    Type(
        "adapter", "Computer & Speicher", "Adapter / Hub / Kartenleser", "CMP",
        (
            F("kind", "Art", "USB-C auf USB-A|USB-Hub|USB-C-Dock|HDMI auf DVI|DisplayPort auf HDMI|"
              "USB-C auf HDMI|Kartenleser|SATA auf USB|USB-Seriell (UART)|Klinke 3.5 auf 6.3|"
              "Reiseadapter|Gender Changer"),
            F("ports", "Anschlüsse", "1|2|3|4|7", hint="Anzahl Ports (Hub)"),
            F("model", "Modell", hint="z. B. CH340, CP2102"),
        ),
        (("{kind}",), ("{ports}-fach",), ("{model}",)),
        extras="netzwerk",
    ),
    Type(
        "pc", "Computer & Speicher", "PC-Komponente / Peripherie", "CMP",
        (
            F("kind", "Art", "Arbeitsspeicher (RAM)|Prozessor|Grafikkarte|PC-Netzteil|Mainboard|"
              "Gehäuselüfter|Tastatur|Maus|Webcam|Monitor|Mini-PC"),
            F("model", "Modell", hint="z. B. DDR4 16GB 3200"),
            F("iface", "Anschluss / Sockel", "USB|DDR4|DDR5|SO-DIMM|AM4|AM5|LGA1700|PCIe|SATA"),
        ),
        (("{kind}",), ("{model}",)),
        extras="netzwerk",
    ),
    # Elektrik & Strom
    Type(
        "akkuzelle", "Akkus & Netzteile", "Akkuzelle (18650, LiPo …)", "ART",
        (
            F("form", "Bauform", "18650|21700|14500|26650|AA|AAA|Pouch (LiPo)|9V|C|D"),
            F("chem", "Chemie", "Li-Ion|LiFePO4|LiPo|NiMH|NiCd"),
            F("cap", "Kapazität", "500|800|1000|2000|2500|3000|3500|5000", "mAh"),
            F("volt", "Nennspannung", "1.2|3.2|3.6|3.7|7.4|11.1", "V"),
            F("prot", "Schutzschaltung", "Geschützt|Ungeschützt|Mit Lötfahne|Flat Top|Button Top", extra=True),
        ),
        (("{form}",), ("{chem}",), ("{cap}mAh",)),
        extras="basis",
    ),
    Type(
        "werkzeugakku", "Akkus & Netzteile", "Werkzeug-Akku", "ART",
        (
            F("brand", "System / Marke", "Makita LXT|Bosch Professional|Bosch Grün|Parkside X20V|"
              "Ryobi ONE+|DeWalt|Einhell Power X-Change|Metabo CAS|Milwaukee"),
            F("volt", "Spannung", "10.8|12|18|20|36|40", "V"),
            F("cap", "Kapazität", "1.5|2|2.5|3|4|5|6|8|12", "Ah"),
        ),
        (("Akku",), ("{brand}",), ("{volt}V",), ("{cap}Ah",)),
        single=True,
        extras="basis",
    ),
    Type(
        "ladegeraet", "Akkus & Netzteile", "Ladegerät", "ART",
        (
            F("kind", "Art", "Akku-Ladegerät (Rundzellen)|Werkzeug-Ladegerät|Modellbau-Lader|"
              "USB-Ladegerät|USB-C PD Ladegerät|Kfz-Ladegerät|Solar-Laderegler|Blei-Ladegerät"),
            F("chem", "Für Chemie", "Li-Ion|LiFePO4|LiPo|NiMH|Blei|Universal"),
            F("power", "Leistung", "10|18|20|30|45|65|100|140", "W"),
            F("slots", "Schächte / Ports", "1|2|4|8", extra=True),
        ),
        (("{kind}",), ("{chem}",), ("{power}W",)),
        extras="basis",
    ),
    Type(
        "steckdosenleiste", "Verbinden & Installation", "Steckdosenleiste / Verlängerung", "ART",
        (
            F("kind", "Art", "Steckdosenleiste|Steckdosenleiste schaltbar|Kabeltrommel|Verlängerung|"
              "Mehrfachstecker|Zwischenstecker|Zeitschaltuhr|Smarte Steckdose"),
            F("sockets", "Steckdosen", "1|2|3|4|5|6|8", row="dim"),
            F("length", "Kabellänge", "1.5|2|3|5|10|25|50", "m", row="dim"),
            F("plug", "Stecker", "Schuko|CEE 16A blau|CEE 16A rot|Euro|Kaltgerät", extra=True),
        ),
        (("{kind}",), ("{sockets}-fach",), ("{length}m",)),
        extras="elektrik",
    ),
    Type(
        "installation", "Verbinden & Installation", "Elektroinstallation (Dose, Schalter, LS)", "CNS",
        (
            F("kind", "Art", "Unterputzdose|Abzweigdose|Aufputzdose|Schalter UP|Steckdose UP|"
              "Leitungsschutzschalter|FI-Schutzschalter|Hutschienenklemme|Mantelleitung NYM|Leerrohr"),
            F("size", "Größe / Typ", "B6|B10|B16|C16|3x1.5|3x2.5|5x2.5|M16|M20|M25|Ø60"),
            F("poles", "Pole", "1|2|3|4", extra=True),
        ),
        (("{kind}",), ("{size}",)),
        extras="elektrik",
    ),
    # Werkzeug & Messen
    Type(
        "gewindebohrer", "Bohren, Fräsen & Sägen", "Gewindebohrer / Schneideisen", "TOL",
        (
            F("kind", "Art", "Gewindebohrer|Maschinengewindebohrer|Handgewindebohrer-Satz|Schneideisen|"
              "Gewindeformer|Gewindereparatur-Satz|Windeisen"),
            F("thread", "Gewinde", THREAD + "|G1/8|G1/4|1/4-20|UNC 6-32"),
            F("material", "Material", "HSS|HSS-E (Co)|HSS-TiN|Hartmetall"),
        ),
        (("{kind}",), ("{thread}",)),
        extras="basis",
    ),
    Type(
        "fraeser", "Bohren, Fräsen & Sägen", "Fräser / Gravierstichel", "TOL",
        (
            F("kind", "Art", "Schaftfräser|Nutfräser|Abrundfräser|Fasefräser|Bündigfräser|"
              "Kugelfräser|V-Nut-Fräser|Gravierstichel|Planfräser|Fräser-Satz"),
            F("dia", "Durchmesser", "1|1.5|2|3|3.175|4|6|8|10|12", "mm", row="dim"),
            F("shank", "Schaft", "3.175|4|6|6.35|8|12", "mm", row="dim"),
            F("flutes", "Schneiden", "1|2|3|4", extra=True),
            F("material", "Material", "Hartmetall|HSS|HM beschichtet|Diamant", extra=True),
        ),
        (("{kind}",), ("Ø{dia}",), ("S{shank}",)),
        extras="basis",
    ),
    Type(
        "saegeblatt", "Bohren, Fräsen & Sägen", "Sägeblatt / Lochsäge", "TOL",
        (
            F("kind", "Art", "Kreissägeblatt|Stichsägeblatt|Säbelsägeblatt|Multitool-Sägeblatt|"
              "Bandsägeblatt|Metallsägeblatt|Japansägeblatt|Lochsäge"),
            F("for", "Für", "Holz|Metall|Kunststoff|Laminat|Alu|Universal|Stein"),
            F("size", "Ø / Länge", "20|32|50|75|100|160|190|210|254", "mm"),
            F("teeth", "Zähne", "24|40|48|60|80", extra=True),
            F("bore", "Aufnahme", "T-Schaft|U-Schaft|Starlock|OIS|16|20|30", extra=True),
        ),
        (("{kind}",), ("{for}",), ("{size}mm",)),
        extras="basis",
    ),
    Type(
        "bit", "Bohren, Fräsen & Sägen", "Bit / Stecknuss", "TOL",
        (
            F("kind", "Art", "Bit|Kraftbit|Stecknuss|Bithalter|Bit-Verlängerung|Steckschlüssel-Adapter"),
            F("profile", "Profil", "PH|PZ|TX|HEX|SL|SW|Vierkant", row="p"),
            F("size", "Größe", "1|2|3|2.5|4|5|6|8|10|13|15|20|25|30|40", row="p"),
            F("length", "Länge", "25|50|75|90|150", "mm"),
            F("drive", "Aufnahme", "1/4 Zoll|3/8 Zoll|1/2 Zoll", extra=True),
        ),
        (("{kind}",), ("{profile}{size}", "{size}"), ("L{length}",)),
        extras="basis",
    ),
    Type(
        "trennscheibe", "Schleifen & Trennen", "Trenn- / Schleifscheibe", "TOL",
        (
            F("kind", "Art", "Trennscheibe|Schruppscheibe|Fächerschleifscheibe|Fiberscheibe|"
              "Diamanttrennscheibe|Klett-Schleifscheibe|Polierscheibe|Drahtbürste|Schleifhülse"),
            F("dia", "Durchmesser", "32|50|76|115|125|150|180|230", "mm"),
            F("for", "Für / Körnung", "Metall|Inox|Stein|Holz|K40|K60|K80|K120|K240"),
        ),
        (("{kind}",), ("Ø{dia}",), ("{for}",)),
        extras="basis",
    ),
    # Material & Chemie
    Type(
        "pinsel", "Farbe & Oberfläche", "Pinsel / Roller", "TOL",
        (
            F("kind", "Art", "Flachpinsel|Rundpinsel|Lackierpinsel|Heizkörperpinsel|Künstlerpinsel|"
              "Farbroller|Schaumstoffroller|Abstreifgitter|Spachtel"),
            F("width", "Breite", "10|20|25|35|50|70|100|180|250", "mm"),
            F("for", "Für", "Lack|Lasur|Dispersion|Öl|Kleber|Harz"),
        ),
        (("{kind}",), ("{width}mm",)),
        extras="basis",
    ),
    Type(
        "reiniger", "Löten, Schmieren & Reinigen", "Reiniger / Lösungsmittel", "CNS",
        (
            F("kind", "Art", "Isopropanol|Aceton|Spiritus|Bremsenreiniger|Waschbenzin|Verdünnung|"
              "Entfetter|Kontaktreiniger|Glasreiniger|Handreiniger|Silikonentferner|Druckluftspray"),
            F("conc", "Konzentration", "70|90|99|99.9", "%"),
            F("content", "Inhalt", "100|250|400|500|1000|5000", "ml"),
        ),
        (("{kind}",), ("{conc}%",), ("{content}ml",)),
        extras="verbrauch",
    ),
    Type(
        "spachtel", "Kleben & Dichten", "Silikon / Acryl / Spachtel", "ART",
        (
            F("kind", "Art", "Sanitärsilikon|Acryl-Fugenmasse|Montagekleber|Holzspachtel|Feinspachtel|"
              "Gips|Bauschaum|Fugenmörtel|Dichtband|Karosseriespachtel"),
            F("color", "Farbe", "Weiß|Transparent|Grau|Braun|Schwarz|Buche|Eiche"),
            F("content", "Inhalt", "100|250|300|310|500|750|1000", "ml/g"),
        ),
        (("{kind}",), ("{color}",), ("{content}ml",)),
        extras="verbrauch",
    ),
    Type(
        "schlauch", "Federn, Dichtungen & Pneumatik", "Schlauch (Wasser, Silikon, PTFE)", "CNS",
        (
            F("kind", "Art", "PVC-Schlauch|Silikonschlauch|PTFE-Schlauch|Gartenschlauch|"
              "Druckluftschlauch|Gewebeschlauch|Benzinschlauch|Vakuumschlauch"),
            F("id", "Innen-Ø", "1.9|2|3|4|5|6|8|10|12|13|19", "mm", row="dim"),
            F("od", "Außen-Ø", "4|5|6|8|10|12|16|20", "mm", row="dim"),
            F("length", "Länge", "0.5|1|2|5|10|25|50", "m"),
        ),
        (("{kind}",), ("{id}x{od}", "Ø{id}"), ("{length}m",)),
        extras="mechanik",
    ),
    # 3D-Druck & Laser
    Type(
        "druckbett", "Druckerteile", "Druckbett / Druckplatte", "CMP",
        (
            F("kind", "Art", "PEI glatt|PEI texturiert|PEI pulverbeschichtet|Glasplatte|G10 / Garolite|"
              "Federstahlblech|Magnetfolie|Heizbett|BuildTak|Kaltplatte"),
            F("size", "Größe", "180x180|220x220|235x235|256x256|300x300|310x310|350x350", "mm"),
        ),
        (("{kind}",), ("{size}",)),
        extras="drucker",
    ),
    Type(
        "heizung", "Druckerteile", "Heizpatrone / Thermistor", "CMP",
        (
            F("kind", "Art", "Heizpatrone|Thermistor NTC 100k|Thermistor 104GT|PT100|PT1000|"
              "Thermoelement Typ K|Heizmatte Silikon|Thermosicherung|Keramikheizer"),
            F("volt", "Spannung", "12|24|230", "V", row="el"),
            F("watt", "Leistung", "30|40|50|60|80|100|200", "W", row="el"),
            F("size", "Maße", "6x15|6x20|6x30|3x15", "mm"),
        ),
        (("{kind}",), ("{volt}V",), ("{watt}W",)),
        extras="drucker",
    ),
    Type(
        "laserplatte", "Laser", "Laser-Platte / Zuschnitt", "RAW",
        (
            F("kind", "Material", "Pappel-Sperrholz|Birke-Sperrholz|MDF|HDF|Acryl klar|Acryl farbig|"
              "Acryl gespiegelt|Leder|Kork|Filz|Karton|Graupappe|Moosgummi|Furnier"),
            F("thickness", "Stärke", "1|1.5|2|3|4|5|6|8|10", "mm"),
            F("size", "Format", "200x300|300x300|300x400|400x400|400x600|600x400|A4|A3"),
            F("color", "Farbe", "Natur|Schwarz|Weiß|Rot|Blau|Grün|Gold|Silber|Transparent"),
        ),
        (("{kind}",), ("{thickness}mm",), ("{size}",)),
        label_lines=("{kind} {thickness}mm", "{size} {color}"),
        extras="material",
    ),
    # Haus & Schutz
    Type(
        "handschuhe", "Schutzausrüstung", "Handschuhe", "PPE",
        (
            F("kind", "Art", "Nitril Einweg|Latex Einweg|Montagehandschuhe|Schnittschutz|"
              "Lederhandschuhe|Hitzeschutz|Chemikalienschutz|Schweißerhandschuhe"),
            F("size", "Größe", "S|M|L|XL|XXL|7|8|9|10|11"),
            F("pack", "Packung", "1 Paar|10|50|100", "Stk"),
        ),
        (("{kind}",), ("{size}",)),
        extras="basis",
    ),
    Type(
        "augenschutz", "Schutzausrüstung", "Schutzbrille / Laserschutz", "PPE",
        (
            F("kind", "Art", "Schutzbrille|Überbrille|Vollsichtbrille|Laserschutzbrille|Gesichtsschutz|"
              "Schweißschirm|Schweißerbrille"),
            F("protect", "Schutzbereich", "Klar|Getönt|190-540 nm OD6+|445 nm OD5+|1064 nm OD6+|"
              "10600 nm (CO2)|DIN 9-13"),
        ),
        (("{kind}",), ("{protect}",)),
        extras="basis",
    ),
    Type(
        "atemschutz", "Schutzausrüstung", "Atemschutz / Filter", "PPE",
        (
            F("kind", "Art", "FFP2-Maske|FFP3-Maske|Halbmaske|Vollmaske|Filter|Vorfilter"),
            F("class", "Klasse / Filter", "FFP2|FFP3|P2|P3|A1|A2|A2P3|ABEK1"),
            F("size", "Größe", "S|M|L", extra=True),
        ),
        (("{kind}",), ("{class}",)),
        extras="basis",
    ),
    Type(
        "gehoerschutz", "Schutzausrüstung", "Gehörschutz", "PPE",
        (
            F("kind", "Art", "Kapselgehörschutz|Ohrstöpsel|Bügelgehörschutz|Otoplastik|Gehörschutz mit Radio"),
            F("snr", "Dämmwert (SNR)", "20|25|28|30|33|37", "dB"),
        ),
        (("{kind}",), ("SNR {snr}",)),
        extras="basis",
    ),
    Type(
        "brandschutz", "Sicherheit & Erste Hilfe", "Feuerlöscher / Melder", "PPE",
        (
            F("kind", "Art", "Feuerlöscher|Löschspray|Löschdecke|Rauchmelder|CO-Melder|Hitzemelder|"
              "Wassermelder"),
            F("agent", "Löschmittel / Klasse", "Schaum AB|Pulver ABC|CO2|Wasser|Fettbrand F|Lithium"),
            F("size", "Inhalt", "0.4 l|1 kg|2 kg|6 kg|6 l|9 l|12 kg"),
            F("due", "Nächste Prüfung", hint="z. B. 2027-03", extra=True),
        ),
        (("{kind}",), ("{agent}",), ("{size}",)),
        single=True,
        extras="basis",
    ),
    Type(
        "erstehilfe", "Sicherheit & Erste Hilfe", "Erste Hilfe", "PPE",
        (
            F("kind", "Art", "Verbandkasten|Pflaster|Pflasterstrips|Mullbinde|Kompresse|Augenspülung|"
              "Brandgel|Kühlpack|Splitterpinzette|Rettungsdecke"),
            F("size", "Größe / Norm", "DIN 13157|DIN 13164|6 cm|8 cm|10 cm"),
            F("expiry", "Haltbar bis", hint="z. B. 2028-06", extra=True),
        ),
        (("{kind}",), ("{size}",)),
        extras="basis",
    ),
    Type(
        "leuchtmittel", "Haushalt, Licht & Sonstiges", "Leuchtmittel", "ART",
        (
            F("kind", "Art", "LED-Lampe|Filament-LED|LED-Röhre|Leuchtstoffröhre|Halogen|Smarte Lampe|"
              "LED-Spot|Glühlampe"),
            F("socket", "Sockel", "E27|E14|GU10|GU5.3|G9|G4|T8|R7s|B22"),
            F("watt", "Leistung", "2|4|5|7|9|12|15|18|24", "W"),
            F("tone", "Lichtfarbe", "Warmweiß 2700K|Warmweiß 3000K|Neutralweiß 4000K|Tageslicht 6500K|RGB"),
        ),
        (("{kind}",), ("{socket}",), ("{watt}W",)),
        extras="basis",
    ),
)
# fmt: on

# --- Optionale Zusatzfelder (eingeklappt unter „Weitere Angaben“) ---------------------------
_BRAND = F("brand", "Hersteller / Marke", extra=True)
_SOURCE = F("source", "Bezugsquelle / Art.-Nr.", extra=True)
_MATERIAL = F(
    "material",
    "Material",
    "Stahl|Edelstahl A2|Edelstahl A4|Messing|Aluminium|Kunststoff|Holz",
    extra=True,
)
_COLOR = F("color", "Farbe", "Schwarz|Weiß|Rot|Blau|Grün|Gelb|Natur|Transparent", extra=True)
_STANDARD = F("standard", "Norm / Serie", extra=True)
_PACK = F("pack", "Packungsgröße", "10|50|100|200|500|1000", "Stk", extra=True)
_NODE = F("node", "Node (Nut-Typ / Einbauort)", hint="für welchen Node / welche Nut", extra=True)

# Profil -> Zusatzfelder. Die Profile der bisherigen Typen entsprechen ihren früheren Gruppen
# (Feld-Schlüssel am Teil bleiben so unverändert).
EXTRAS: dict[str, tuple[Field, ...]] = {
    "befestigung": (
        F(
            "standard",
            "Norm",
            "DIN 912|DIN 933|DIN 7991|DIN 7380|DIN 934|DIN 985|DIN 125|ISO 4762|ISO 10642",
            extra=True,
        ),
        F("strength", "Festigkeitsklasse", "4.6|5.8|8.8|10.9|12.9|A2-70|A4-80", extra=True),
        F(
            "coating",
            "Beschichtung",
            "Blank|Verzinkt|Schwarz oxidiert|Geomet|Vernickelt|Gelb chromatiert",
            extra=True,
        ),
        F("pitch", "Steigung", "Regelgewinde|Feingewinde", extra=True),
        F("threadlen", "Gewindelänge", "Vollgewinde|Teilgewinde", extra=True),
        _PACK,
        _NODE,
        _BRAND,
        _SOURCE,
    ),
    "verbrauch": (
        F("content", "Inhalt", "5|10|20|50|100|250|500", "ml/g", extra=True),
        F("cure", "Aushärtezeit", "5 min|30 min|24 h", extra=True),
        F("temp", "Temperaturbereich", "", "°C", extra=True),
        _COLOR,
        _BRAND,
        _SOURCE,
    ),
    "mechanik": (
        _MATERIAL,
        F("load", "Belastbarkeit", "", "N", extra=True),
        _STANDARD,
        _BRAND,
        _SOURCE,
    ),
    "elektrik": (
        _COLOR,
        F("rated", "Nennstrom", "1|2|3|5|10|16", "A", extra=True),
        F("rvolt", "Nennspannung", "5|12|24|48|230", "V", extra=True),
        _BRAND,
        _SOURCE,
    ),
    "elektronik": (
        F(
            "package",
            "Bauform / Gehäuse",
            "THT|SMD 0603|SMD 0805|SMD 1206|SOT-23|SOIC-8|DIP-8|TO-220|TO-92",
            extra=True,
        ),
        F("tolerance", "Toleranz", "1%|5%|10%|20%", extra=True),
        F("rating", "Belastbarkeit", "", "W/V/A", extra=True),
        _BRAND,
        _SOURCE,
    ),
    "werkzeug": (F("size", "Größe", extra=True), _MATERIAL, _BRAND, _SOURCE),
    "drucker": (
        F(
            "compat",
            "Passend für",
            "Voron|Bambu Lab|Prusa|Creality|Ender|Laser|Allgemein",
            extra=True,
        ),
        _MATERIAL,
        _BRAND,
        _SOURCE,
    ),
    "material": (F("dims", "Maße", extra=True), _MATERIAL, _COLOR, _BRAND, _SOURCE),
    "netzwerk": (_COLOR, _BRAND, _SOURCE),
    "kleinteile": (_STANDARD, _PACK, _BRAND, _SOURCE),
    "basis": (_BRAND, _SOURCE),
}


def _with_extras(types: tuple[Type, ...]) -> tuple[Type, ...]:
    out = []
    for t in types:
        have = {f.key for f in t.fields}
        add = tuple(f for f in EXTRAS[t.extras] if f.key not in have)
        out.append(replace(t, fields=t.fields + add) if add else t)
    return tuple(out)


# Bisherige Typen bewerten in `guess` wie bisher (kurze Werte dürfen mehrfach zählen); neue Typen
# zählen jeden kurzen Wert nur einmal, damit z. B. „5-polig“ keine Maß-Felder doppelt trifft.
_LEGACY_KEYS = frozenset(t.key for t in TYPES)
TYPES = _with_extras(TYPES + TYPES_2_0)


BY_KEY = {t.key: t for t in TYPES}


CUSTOM_GROUP = "Eigene Typen"
FAVORITES = "Favoriten"


DEFAULT_NODES = (
    "Nut 5", "Nut 6", "Nut 8", "Nut 10", "Profil 2020", "Profil 3030", "Profil 4040", "Holz",
    "3D-Druckteil", "Blech", "Kunststoff",
)  # fmt: skip


def node_types(conn: sqlite3.Connection | None) -> list[str]:
    """Eigene Node-Liste (Einstellungen -> Admin), sonst die Standardliste."""
    raw = codes.get_setting(conn, "node_types", "") if conn is not None else ""
    custom = [x.strip() for x in raw.splitlines() if x.strip()]
    return custom or list(DEFAULT_NODES)


def brands(conn: sqlite3.Connection | None, t: Type) -> list[str]:
    """Hersteller-Auswahl: Katalogliste + alles, was je manuell eingetragen wurde."""
    base = next((f.options for f in t.fields if f.key == "brand"), ())
    raw = codes.get_setting(conn, f"brands_{t.key}", "") if conn is not None else ""
    manual = [x.strip() for x in raw.split("|") if x.strip()]
    return list(dict.fromkeys([*base, *manual]))


def remember_brand(conn: sqlite3.Connection, t: Type, brand: str) -> None:
    """Manuell eingetragener Hersteller wird künftig in Auswahl und Presets angeboten."""
    brand = brand.strip()
    if not brand or brand.casefold() in {b.casefold() for b in brands(conn, t)}:
        return
    if not any(f.key == "brand" for f in t.fields):
        return
    manual = [b for b in codes.get_setting(conn, f"brands_{t.key}", "").split("|") if b]
    codes.set_setting(conn, f"brands_{t.key}", "|".join([*manual, brand]))


def field_choices() -> list[tuple[str, str]]:
    """Alle Feld-Schlüssel der Katalogtypen (für die Sammelbearbeitung)."""
    seen: dict[str, str] = {}
    for t in TYPES:
        for f in t.fields:
            seen.setdefault(f.key, f.label)
    return sorted(seen.items(), key=lambda kv: kv[1].lower())


def options_for(
    conn: sqlite3.Connection | None, f: Field, t: Type | None = None
) -> tuple[str, ...]:
    if f.key == "node":
        return tuple(node_types(conn))
    if f.key == "brand" and t is not None:
        return tuple(brands(conn, t))
    return f.options


def area_of(t: Type) -> str:
    """Bereich eines Typs; eigene Typen stehen immer im Bereich „Eigene Typen“."""
    return AREA_OF.get(t.group, CUSTOM_GROUP) if t.key in BY_KEY else CUSTOM_GROUP


def grouped(conn: sqlite3.Connection | None = None) -> list[tuple[str, list[Type]]]:
    """Flache Liste (Gruppe, Typen) – Favoriten zuerst, eigene Typen am Ende."""
    out = [(g, [t for t in TYPES if t.group == g]) for g in GROUPS]
    if conn is None:
        return out
    mine = custom_types(conn)
    groups = list(dict.fromkeys(t.group for t in mine))
    out += [(g, [t for t in mine if t.group == g]) for g in groups]
    favs = favorite_keys(conn)  # Favoriten: je Gruppe ganz oben, dazu eine Gruppe „Favoriten“
    out = [(g, sorted(ts, key=lambda t: t.key not in favs)) for g, ts in out]
    top = [t for _g, ts in out for t in ts if t.key in favs]
    return ([(FAVORITES, top)] if top else []) + out


def areas(
    conn: sqlite3.Connection | None = None,
) -> list[tuple[str, list[tuple[str, list[Type]]]]]:
    """Zwei Ebenen: [(Bereich, [(Gruppe, Typen)])]. Favoriten bilden einen eigenen Bereich
    ganz oben, eigene Typen den Bereich „Eigene Typen“ am Ende; leere Gruppen entfallen."""
    out: dict[str, list[tuple[str, list[Type]]]] = {}
    for g, ts in grouped(conn):
        if not ts:
            continue
        area = FAVORITES if g == FAVORITES else area_of(ts[0])
        out.setdefault(area, []).append((g, ts))
    return list(out.items())


def area_groups(conn: sqlite3.Connection | None = None) -> list[tuple[str, list[Type]]]:
    """Flache Liste für Auswahllisten (optgroup): („Bereich › Gruppe“, Typen)."""
    return [(g if g == a else f"{a} › {g}", ts) for a, gs in areas(conn) for g, ts in gs]


def favorite_keys(conn: sqlite3.Connection) -> set[str]:
    return {k for k in codes.get_setting(conn, "fav_types", "").split(",") if k}


def toggle_favorite(conn: sqlite3.Connection, key: str) -> bool:
    """Typ als Favorit markieren oder wieder lösen; liefert den neuen Zustand."""
    favs = favorite_keys(conn)
    on = key not in favs
    favs = favs | {key} if on else favs - {key}
    codes.set_setting(conn, "fav_types", ",".join(sorted(favs)))
    return on


# --- Eigene Typen ------------------------------------------------------------------------


def slug(text: str) -> str:
    table = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    return re.sub(r"[^a-z0-9]+", "_", text.casefold().translate(table)).strip("_")[:30]


def _custom(row: sqlite3.Row) -> Type:
    fields = tuple(
        Field(f["key"], f["label"], tuple(f.get("options", ())), f.get("unit", ""))
        for f in json.loads(row["fields"] or "[]")
    )
    tpl = row["name_tpl"].strip() or " ".join("{" + f.key + "}" for f in fields)
    parts = tuple((part,) for part in tpl.split())
    return Type(row["key"], row["grp"] or CUSTOM_GROUP, row["label"], row["cat"], fields, parts)


def custom_types(conn: sqlite3.Connection) -> list[Type]:
    rows = conn.execute("SELECT * FROM custom_type ORDER BY grp, label COLLATE NOCASE").fetchall()
    return [_custom(r) for r in rows]


def lookup(conn: sqlite3.Connection | None, key: str) -> Type | None:
    """Katalog-Typ oder eigener Typ."""
    if key in BY_KEY:
        return BY_KEY[key]
    if conn is None or not key:
        return None
    row = conn.execute("SELECT * FROM custom_type WHERE key = ?", (key,)).fetchone()
    return _custom(row) if row else None


def parse_field_lines(text: str) -> list[dict[str, object]]:
    """Formular „Feldname | Option, Option | Einheit“ (eine Zeile je Feld) -> Feldliste."""
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if not parts[0]:
            continue
        key = slug(parts[0]) or f"f{len(out) + 1}"
        if any(f["key"] == key for f in out):
            raise LagerError(f"Feld „{parts[0]}“ doppelt")
        options = [o.strip() for o in parts[1].split(",") if o.strip()] if len(parts) > 1 else []
        out.append({"key": key, "label": parts[0], "options": options,
                    "unit": parts[2] if len(parts) > 2 else ""})  # fmt: skip
    if not out:
        raise LagerError("Mindestens ein Feld angeben")
    return out


def save_custom(
    conn: sqlite3.Connection,
    label: str,
    fields_text: str,
    cat: str = "ART",
    group: str = "",
    name_tpl: str = "",
    key: str = "",
) -> str:
    """Eigenen Typ anlegen oder (mit `key`) ändern; gibt den Schlüssel zurück."""
    if not label.strip():
        raise LagerError("Name des Typs fehlt")
    cat = cat.strip().upper() or "ART"
    if cat not in codes.ITEM_PREFIXES:
        raise LagerError(f"Unbekannte Kategorie {cat}")
    fields = parse_field_lines(fields_text)
    for ref in re.findall(r"{(\w+)}", name_tpl):
        if ref not in {f["key"] for f in fields}:
            raise LagerError(f"Namensvorlage nutzt unbekanntes Feld {{{ref}}}")
    key = key or "c_" + slug(label)
    if not key or key == "c_":
        raise LagerError("Name des Typs ungültig")
    if key in BY_KEY:
        raise LagerError("Diesen Namen hat schon ein Katalog-Typ")
    with conn:
        conn.execute(
            "INSERT INTO custom_type (key, label, grp, cat, fields, name_tpl) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET label = excluded.label, grp = excluded.grp,"
            " cat = excluded.cat, fields = excluded.fields, name_tpl = excluded.name_tpl",
            (key, label.strip(), group.strip() or CUSTOM_GROUP, cat,
             json.dumps(fields, ensure_ascii=False), name_tpl.strip()),
        )  # fmt: skip
    return key


def delete_custom(conn: sqlite3.Connection, key: str) -> int:
    """Eigenen Typ löschen; Teile behalten Name und Felder, verlieren nur die Typ-Zuordnung."""
    with conn:
        n = conn.execute("UPDATE item SET ctype = NULL WHERE ctype = ?", (key,)).rowcount
        conn.execute("DELETE FROM custom_type WHERE key = ?", (key,))
    return n


def field_lines(t: Type) -> str:
    """Rückweg fürs Bearbeiten-Formular."""
    return "\n".join(
        " | ".join(x for x in (f.label, ", ".join(f.options), f.unit) if x) if f.unit
        else " | ".join(x for x in (f.label, ", ".join(f.options)) if x)
        for f in t.fields
    )  # fmt: skip


ADDITIVE_SHORT = {"glasfaser": "GF", "carbonfaser": "CF", "kohlefaser": "CF"}


def derive(t: Type, values: dict[str, str]) -> dict[str, str]:
    """Abgeleitete Werte: Filament-Werkstoff = „PA12 80 % + CF 20 %“ aus Kunststoff/Zusatz."""
    if t.key != "filament":
        return values
    plastic = values.get("plastic", "").strip()
    add = values.get("additive", "").strip()
    pct_raw = values.get("additive_pct", "").strip().rstrip("%").strip()
    try:
        pct = float(pct_raw) if pct_raw else None
    except ValueError:
        pct = None
    text = plastic
    if add:
        short = ADDITIVE_SHORT.get(add.casefold(), add)
        if pct is not None and plastic and 0 < pct < 100:  # Kunststoff = 100 − Zusatz
            text = f"{plastic} {100 - pct:g}% + {short} {pct:g}%"
        else:
            text = f"{plastic} + {short}".strip(" +")
    return {**values, "material": text} if text else values


def number(raw: str) -> str:
    """Dezimalzahlen immer mit Punkt: „1,75“ -> „1.75“ (Komma zwischen Ziffern)."""
    return re.sub(r"(?<=\d),(?=\d)", ".", raw)


def field_rows(fields: list[Field] | tuple[Field, ...]) -> list[list[Field]]:
    """Felder zu Formularzeilen: aufeinanderfolgende Felder mit gleicher `row` stehen nebeneinander."""
    out: list[list[Field]] = []
    for f in fields:
        if out and f.row and out[-1][-1].row == f.row:
            out[-1].append(f)
        else:
            out.append([f])
    return out


def name(t: Type, values: dict[str, str]) -> str:
    """Name aus den Vorlagen: pro Teil die erste Alternative, deren Felder alle ausgefüllt sind."""
    values = derive(t, values)
    out = []
    for alts in t.parts:
        for alt in (alts,) if isinstance(alts, str) else alts:
            keys = re.findall(r"{(\w+)}", alt)
            if all(values.get(k, "").strip() for k in keys):
                out.append(alt.format(**{k: values[k].strip() for k in keys}))
                break
    return " ".join(out).strip()


def types_json() -> dict[str, list[str]]:
    return {t.key: [f.key for f in t.fields] for t in TYPES}


def create(
    conn: sqlite3.Connection,
    type_key: str,
    values: dict[str, str],
    container_id: int,
    qty: int | None = None,
    standalone: bool = True,
) -> int:
    t = lookup(conn, type_key)
    if t is None:
        raise LagerError("Unbekannter Teile-Typ")
    clean = derive(t, {f.key: number(values.get(f.key, "")).strip() for f in t.fields})
    text = name(t, clean)
    if not text:
        raise LagerError(f"Bitte mindestens ein Feld für „{t.label}“ ausfüllen")
    code = (
        None
        if not standalone  # Fachinhalt ohne eigenes Etikett: nur Tags, kein Code
        else codes.new_item_code(conn)
        if t.cat == codes.ITEM_PREFIX
        else codes.reserve(conn, t.cat, 1)[0]
    )
    tags = auto_tags(t, clean)
    item_id = repo.add_item(conn, container_id, text, qty=qty, code=code, tags=tags)
    if not standalone:
        with conn:
            conn.execute("UPDATE item SET standalone = 0 WHERE id = ?", (item_id,))
    store(conn, item_id, t.key, clean)
    profile, spec = type_specs(t, clean)
    if profile:
        materials.save_specs(conn, item_id, profile, spec)
    if clean.get("price"):
        repo.update_item(conn, item_id, price=materials.parse_price(clean["price"]))
    remember_brand(conn, t, clean.get("brand", ""))
    return item_id


def profile_of(t: Type | None) -> str:
    """Eigenschafts-Profil, das der Typ festlegt (Elektronik -> cmp, Filament -> fil …)."""
    if t is None:
        return ""
    return t.material or ("cmp" if t.cmp else "")


def spec_keys(t: Type) -> set[str]:
    """Datenblatt-Felder, die schon über die Typ-Felder befüllt werden."""
    profile = profile_of(t)
    if not profile:
        return set()
    own = {f.key for f in t.fields} | ({"material"} if t.key == "filament" else set())
    return own & {f.key for f in materials.FIELDS[profile]}


def type_specs(t: Type, clean: dict[str, str]) -> tuple[str, dict[str, str]]:
    """(Profil, Formularwerte spec_*) aus den Typ-Feldern – fürs Datenblatt und Restmengen."""
    profile = profile_of(t)
    if not profile:
        return "", {}
    keys = {f.key for f in materials.FIELDS[profile]}
    spec = {f"spec_{k}": v for k, v in clean.items() if v and k in keys}
    if t.cmp:
        spec["spec_function"] = " ".join(p for p in (t.label, clean.get("kind", "")) if p)
    if t.key == "filament" and spec.get("spec_weight"):  # Katalog in kg, Datenblatt in g
        with contextlib.suppress(ValueError):
            spec["spec_weight"] = f"{float(spec['spec_weight']) * 1000:g}"
    return profile, spec


PROFILE_TAGS = {
    "befestigung": "befestigung verbindung",
    "kleinteile": "befestigung",
    "verbrauch": "verbrauchsmaterial",
    "mechanik": "mechanik",
    "elektrik": "elektrik kabel",
    "elektronik": "elektronik bauteil",
    "werkzeug": "werkzeug",
    "drucker": "3d-druck laser drucker",
    "material": "rohmaterial",
    "netzwerk": "netzwerk lan it",
}
# Wert (Teilstring, klein) -> zusätzliche Tags
VALUE_TAGS = (
    (("edelstahl", "a2", "a4", "v2a"), "edelstahl rostfrei"),
    (("verzinkt", "zink"), "verzinkt"),
    (("messing",), "messing metall"),
    (("alu",), "aluminium metall"),
    (("nylon", "pa6", "pa12"), "kunststoff"),
    (("petg", "pla", "abs", "asa", "tpu"), "filament 3d-druck"),
    (("12v", "24v", "5v", "3.3v", "3,3v"), "spannung"),
    (("usb",), "usb"),
    (("rj45", "cat5", "cat6", "cat7"), "ethernet netzwerk"),
    (("led",), "beleuchtung led"),
    (("torx", "tx"), "torx"),
    (("innensechskant", "imbus"), "innensechskant imbus"),
    (("senk",), "senkkopf"),
)


def auto_tags(t: Type, values: dict[str, str]) -> str:
    """Tags automatisch: Typ, Gruppe, Feldwerte und Stichwort-Regeln (ohne Doppelte)."""
    words = [t.label.lower(), PROFILE_TAGS.get(t.extras, t.group.lower())]
    words += [v.lower() for v in values.values() if v]
    blob = " ".join(words)
    for needles, extra in VALUE_TAGS:
        if any(n in blob for n in needles):
            words.append(extra)
    return " ".join(dict.fromkeys(" ".join(words).split()))


def quick_options() -> list[tuple[str, list[tuple[str, str]]]]:
    """Für die Fachzeilen im Einsatz-Assistenten: (Gruppe, [(Wert, Anzeige)])."""
    out = []
    for group, types in grouped():
        opts = []
        for t in types:
            first = t.fields[0]
            for o in first.options:
                opts.append((f"{t.key}|{o}", o))
        if opts:
            out.append((group, opts))
    return out


def suggestions() -> dict[str, list[str]]:
    """Variantenvorschläge je Typ (zweites Feld mit Auswahl, z. B. Gewinde)."""
    out: dict[str, list[str]] = {}
    for t in TYPES:
        extra = next((f for f in t.fields[1:] if f.options and not f.extra), None)
        out[t.key] = list(extra.options) if extra else []
    return out


def create_quick(
    conn: sqlite3.Connection,
    type_key: str,
    art: str,
    variant: str,
    container_id: int,
    qty: int | None = None,
) -> int:
    """Teil aus Art + Variante („Zylinderkopfschraube“ + „M3x10“) – für Fächer im Einsatz."""
    t = lookup(conn, type_key)
    if t is None:
        raise LagerError("Unbekannter Teile-Typ")
    text = f"{art} {variant}".strip()
    code = (
        codes.new_item_code(conn)
        if t.cat == codes.ITEM_PREFIX
        else codes.reserve(conn, t.cat, 1)[0]
    )
    tags = " ".join(x.lower() for x in (t.label, art, variant) if x)
    item_id = repo.add_item(conn, container_id, text, qty=qty, code=code, tags=tags)
    vals = {t.fields[0].key: art} if t.fields and art else {}
    if variant and len(t.fields) > 1:
        vals.update(split_variant(t, variant))
    store(conn, item_id, t.key, vals)
    if t.cmp:
        materials.save_specs(conn, item_id, "cmp", {"spec_function": f"{t.label} {art}".strip()})
    return item_id


# --- Typ am Teil: speichern, bearbeiten, Dubletten ---------------------------------------------


def store(conn: sqlite3.Connection, item_id: int, key: str, values: dict[str, str]) -> None:
    clean = {k: v.strip() for k, v in values.items() if v and v.strip()}
    with conn:
        conn.execute(
            "UPDATE item SET ctype = ?, cfields = ? WHERE id = ?",
            (key, json.dumps(clean, ensure_ascii=False), item_id),
        )


def values_of(item: sqlite3.Row) -> dict[str, str]:
    try:
        data = json.loads(item["cfields"] or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def split_variant(t: Type, variant: str) -> dict[str, str]:
    """„M3x10“ -> thread/length, sonst die Variante ins zweite Feld."""
    keys = [f.key for f in t.fields]
    m = re.fullmatch(r"\s*(M\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*", variant, re.I)
    if m and "thread" in keys and "length" in keys:
        return {"thread": m.group(1).upper(), "length": m.group(2)}
    return {keys[1]: variant.strip()}


def set_fields(
    conn: sqlite3.Connection, item_id: int, key: str, values: dict[str, str], rename: bool = True
) -> str:
    """Typ und Felder am Teil setzen; optional Namen aus den Feldern neu bilden."""
    t = lookup(conn, key)
    if t is None:
        raise LagerError("Unbekannter Teile-Typ")
    allowed = {f.key for f in t.fields}
    clean = {k: v.strip() for k, v in values.items() if k in allowed}
    store(conn, item_id, key, clean)
    new_name = name(t, clean)
    if rename and new_name:
        tags = " ".join(v.lower() for v in (t.label, *clean.values()) if v)
        repo.update_item(conn, item_id, name=new_name, tags=tags)
    return new_name


def _norm(values: dict[str, str]) -> dict[str, str]:
    return {k: v.strip().casefold().replace(",", ".") for k, v in values.items() if v.strip()}


def duplicates(conn: sqlite3.Connection, key: str, values: dict[str, str]) -> list[sqlite3.Row]:
    """Teile desselben Typs mit genau denselben ausgefüllten Feldern (nicht archiviert)."""
    want = _norm(values)
    if not want:
        return []
    rows = conn.execute(
        "SELECT * FROM item WHERE ctype = ? AND archived = 0 ORDER BY id", (key,)
    ).fetchall()
    return [r for r in rows if _norm(values_of(r)) == want]


# --- Altbestand: Typ und Felder aus dem Namen erkennen (regelbasiert) ------------------------


def _label_words(t: Type) -> list[str]:
    words = re.findall(r"[a-zäöüß]{4,}", t.label.casefold())
    return [w.removesuffix("en").removesuffix("e") if len(w) > 6 else w for w in words]


_NUM = r"\d+(?:[.,]\d+)?"


def _option_re(option: str, legacy: bool = False) -> str:
    """Suchmuster für einen Auswahlwert; bei neuen Typen Zahlen nicht mitten in anderen Zahlen
    („5“ in „0.5“). Bisherige Typen behalten ihr altes Muster (Ergebnisse bleiben gleich)."""
    o = re.escape(option.casefold())
    if option[:1].isdigit() and not legacy:
        return rf"(?<![\w.,]){o}(?![\w]|[.,]\d)"
    return rf"(?<![\w]){o}(?![\w])"


def _slot(options: tuple[str, ...]) -> str:
    """Platzhalter im Vorlagen-Muster: Zahl oder einer der (nicht-numerischen) Auswahlwerte."""
    words = [re.escape(o.casefold()) for o in options if not re.fullmatch(_NUM, o)]
    return "(" + "|".join([*sorted(words, key=len, reverse=True), _NUM]) + ")"


def _template_res(t: Type) -> list[tuple[str, list[str]]]:
    """Muster aus der Namensvorlage für Maßangaben wie „{width}mm“, „Ø{od}“ oder „{id}x{od}“."""
    out = []
    for alts in t.parts:
        for alt in (alts,) if isinstance(alts, str) else alts:
            keys = re.findall(r"{(\w+)}", alt)
            literal = re.sub(r"{\w+}", "", alt).strip()
            if not keys or not literal or " " in alt:
                continue
            opts = {f.key: f.options for f in t.fields}
            pattern = "".join(
                _slot(opts.get(p[1:-1], ())) if p.startswith("{") else re.escape(p.casefold())
                for p in re.split(r"({\w+})", alt)
                if p
            )
            out.append((rf"(?<![\w.,]){pattern}(?![\w])", keys))
    return out


def guess(conn: sqlite3.Connection | None, text: str) -> tuple[str, dict[str, str], int] | None:
    """(Typ, Felder, Punkte) für einen vorhandenen Teilenamen – oder None, wenn nichts passt."""
    low = text.casefold()
    best: tuple[str, dict[str, str], int] | None = None
    types = list(TYPES) + (custom_types(conn) if conn is not None else [])
    for t in types:
        score, vals, seen = 0, {}, set()
        legacy = t.key in _LEGACY_KEYS
        if any(w in low for w in _label_words(t)):
            score += 3
        for f in t.fields:
            hits = [o for o in f.options if re.search(_option_re(o, legacy), low)]
            if hits:
                vals[f.key] = max(hits, key=len)
                short = len(vals[f.key]) < 4
                if not short or legacy or vals[f.key].casefold() not in seen:
                    seen.add(vals[f.key].casefold())
                    score += 2 if short else 3
        if not legacy:  # Maße aus der Namensvorlage („6mm“, „Ø8“, „5x2“)
            for pattern, tkeys in _template_res(t):
                if (tm := re.search(pattern, low)) and not all(k in vals for k in tkeys):
                    vals.update({k: v for k, v in zip(tkeys, tm.groups(), strict=True)})
                    score += 2
        keys = {f.key for f in t.fields}
        m = re.search(r"\b(m\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\b", low)
        if m and {"thread", "length"} <= keys:
            vals["thread"], vals["length"] = m.group(1).upper(), m.group(2)
            score += 3
        elif (m2 := re.search(r"\b(m\d+(?:[.,]\d+)?)\b", low)) and "thread" in keys:
            vals.setdefault("thread", m2.group(1).upper())
            score += 1
        if score >= 4 and (best is None or score > best[2]):
            best = (t.key, vals, score)
    return best
