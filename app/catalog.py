# ruff: noqa: E501
"""Teile-Katalog: häufige Teile (Heimwerken, 3D-Druck, Laser, Elektronik) mit Auswahlfeldern.

Jeder Typ hat Felder (Auswahl + freie Eingabe) und eine Namensvorlage; daraus entsteht der
Teilename wie im Lager üblich („Zylinderkopfschraube M3x10“, „Holzinsert M4“). Es geht um
schnelles Anlegen, nicht um exakte Erfassung – Details lassen sich am Teil nachtragen.
"""

import re
import sqlite3
from dataclasses import dataclass

from app import codes, materials, repo
from app.repo import LagerError


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    options: tuple[str, ...] = ()
    unit: str = ""
    hint: str = ""


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


def F(key: str, label: str, options: str = "", unit: str = "", hint: str = "") -> Field:
    return Field(key, label, tuple(o.strip() for o in options.split("|") if o.strip()), unit, hint)


THREAD = "M2|M2.5|M3|M4|M5|M6|M8|M10|M12"
LENGTH = "4|5|6|8|10|12|16|20|25|30|35|40|50|60"

GROUPS = (
    "Schrauben & Befestigung", "Klebstoff & Verbrauch", "Mechanik & Pneumatik",
    "Kabel & Elektrik", "Elektronik", "Werkzeug", "3D-Druck & Laser", "Material & Holz",
)  # fmt: skip

TYPES: tuple[Type, ...] = (
    # --- Schrauben & Befestigung -------------------------------------------------
    Type(
        "schraube",
        GROUPS[0],
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
    ),
    Type(
        "mutter",
        GROUPS[0],
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
    ),
    Type(
        "insert",
        GROUPS[0],
        "Einschmelzmutter / Insert",
        "CNS",
        (
            F("kind", "Art", "Heat-Set Insert|Holzinsert|Aluinsert|Einpressmutter|Gewindeeinsatz"),
            F("thread", "Gewinde", THREAD),
            F("length", "Länge", "3|4|5|6|8|10|12", "mm"),
        ),
        (("{kind}",), ("{thread}",), ("L{length}",)),
    ),
    Type(
        "scheibe",
        GROUPS[0],
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
            F("finish", "Material", "Edelstahl|Verzinkt|Nylon|Messing"),
        ),
        (("{kind}",), ("{thread}",)),
    ),
    Type(
        "holzschraube",
        GROUPS[0],
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
    ),
    Type(
        "duebel",
        GROUPS[0],
        "Dübel",
        "CNS",
        (
            F("kind", "Art", "Spreizdübel|Universaldübel|Holzdübel|Hohlraumdübel|Rahmendübel"),
            F("size", "Maße", "5x25|6x30|8x40|10x50|6x30 Holz|8x40 Holz", "mm"),
        ),
        (("{kind}",), ("{size}",)),
    ),
    Type(
        "gewindestange",
        GROUPS[0],
        "Gewindestange / Stift",
        "CNS",
        (
            F("kind", "Art", "Gewindestange|Passstift|Stahlstift|Splint|Niete"),
            F("thread", "Gewinde / Ø", THREAD),
            F("length", "Länge", "100|200|300|500|1000", "mm"),
        ),
        (("{kind}",), ("{thread}x{length}", "{thread}")),
    ),
    Type(
        "kleinteil",
        GROUPS[0],
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
    ),
    # --- Klebstoff & Verbrauch ------------------------------------------------------
    Type(
        "kleber",
        GROUPS[1],
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
    ),
    Type(
        "klebeband",
        GROUPS[1],
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
    ),
    Type(
        "loeten",
        GROUPS[1],
        "Löten (Zinn, Flussmittel …)",
        "CNS",
        (
            F("kind", "Art", "Lötzinn|Flussmittel|Entlötlitze|Lötfett|Lötspitze|Wärmeleitpaste"),
            F("size", "Stärke / Variante", "0.5 mm|0.8 mm|1.0 mm|100 g|250 g|bleifrei"),
        ),
        (("{kind}",), ("{size}",)),
    ),
    Type(
        "schmierung",
        GROUPS[1],
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
    ),
    Type(
        "batterie",
        GROUPS[1],
        "Batterie / Akku",
        "CNS",
        (
            F("kind", "Typ", "AA|AAA|9V Block|CR2032|CR2025|LR44|18650|LiPo"),
            F("brand", "Marke", "Varta|Duracell|Energizer|Basic"),
        ),
        (("{kind}",), ("{brand}",)),
    ),
    Type(
        "schleifen",
        GROUPS[1],
        "Schleifmittel",
        "CNS",
        (
            F("kind", "Art", "Schleifpapier|Schleifvlies|Schleifband|Feile|Polierpaste"),
            F("grit", "Körnung", "80|120|180|240|320|400|600|800|1000|2000"),
        ),
        (("{kind}",), ("K{grit}",)),
    ),
    # --- Mechanik & Pneumatik ------------------------------------------------------
    Type(
        "lager",
        GROUPS[2],
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
    ),
    Type(
        "kupplung",
        GROUPS[2],
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
    ),
    Type(
        "pneumatik",
        GROUPS[2],
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
    ),
    Type(
        "magnet",
        GROUPS[2],
        "Magnet",
        "CNS",
        (
            F("kind", "Art", "Neodym Scheibe|Neodym Quader|Neodym Kugel|Topfmagnet|Ferrit"),
            F("size", "Maße", "5x2|10x3|10x5|20x5|20x10|30x5", "mm"),
        ),
        (("{kind}",), ("{size}",)),
    ),
    Type(
        "profil",
        GROUPS[2],
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
    ),
    # --- Kabel & Elektrik -----------------------------------------------------------
    Type(
        "schrumpf",
        GROUPS[3],
        "Schrumpfschlauch",
        "CNS",
        (
            F("dia", "Durchmesser", "1.0-2.0|3.0|4.0|5.0|6.0|8.0|10.0|12.0|20.0", "mm"),
            F("color", "Farbe", "Schwarz|Rot|Blau|Transparent|Gelb"),
        ),
        (("Schrumpfschlauch {dia}",), ("{color}",)),
    ),
    Type(
        "huelse",
        GROUPS[3],
        "Aderendhülse",
        "CNS",
        (F("size", "Querschnitt", "0.5|0.75|1.0|1.5|2.5|4.0|6.0|Sortiment", "mm²"),),
        (("Aderendhülse {size}",),),
    ),
    Type(
        "kabelschuh",
        GROUPS[3],
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
    ),
    Type(
        "klemme",
        GROUPS[3],
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
    ),
    Type(
        "sicherung",
        GROUPS[3],
        "Sicherung",
        "CNS",
        (
            F("kind", "Art", "Glassicherung 5x20|Glassicherung 6.3x32|Flachsicherung|Polyswitch"),
            F("amp", "Strom", "0.5|1|2|3.15|5|10|16", "A"),
        ),
        (("{kind}",), ("{amp}A",)),
    ),
    # --- Elektronik (Datenblatt-Profil Elektronikbauteil) -----------------------------
    Type(
        "mcu",
        GROUPS[4],
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
    ),
    Type(
        "sensor",
        GROUPS[4],
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
    ),
    Type(
        "aktor",
        GROUPS[4],
        "Aktor / Motor",
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
    ),
    Type(
        "anzeige",
        GROUPS[4],
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
    ),
    Type(
        "schalter",
        GROUPS[4],
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
    ),
    Type(
        "treiber",
        GROUPS[4],
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
    ),
    Type(
        "strom",
        GROUPS[4],
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
    ),
    Type(
        "funk",
        GROUPS[4],
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
    ),
    Type(
        "led",
        GROUPS[4],
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
    ),
    Type(
        "passiv",
        GROUPS[4],
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
    ),
    Type(
        "halbleiter",
        GROUPS[4],
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
    ),
    Type(
        "stecker",
        GROUPS[4],
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
    ),
    Type(
        "proto",
        GROUPS[4],
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
    ),
    Type(
        "smarthome",
        GROUPS[4],
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
    ),
    # --- Werkzeug ---------------------------------------------------------------------
    Type(
        "zange",
        GROUPS[5],
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
    ),
    Type(
        "schrauber",
        GROUPS[5],
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
    ),
    Type(
        "bohrer",
        GROUPS[5],
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
    ),
    Type(
        "messen",
        GROUPS[5],
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
    ),
    Type(
        "schneiden",
        GROUPS[5],
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
    ),
    Type(
        "werkzeug_sonst",
        GROUPS[5],
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
    ),
    # --- 3D-Druck & Laser ---------------------------------------------------------------
    Type(
        "duese",
        GROUPS[6],
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
    ),
    Type(
        "druckerteil",
        GROUPS[6],
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
    ),
    Type(
        "laser",
        GROUPS[6],
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
    ),
    Type(
        "etiketten",
        GROUPS[6],
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
    ),
    # --- Material & Holz -----------------------------------------------------------------
    Type(
        "holz",
        GROUPS[7],
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
    ),
    Type(
        "metall",
        GROUPS[7],
        "Metall / Kunststoff",
        "RAW",
        (
            F("kind", "Art", "Aluminium|Stahl|Edelstahl|Messing|Kupfer|Acryl|PVC|POM|Polycarbonat"),
            F("form", "Form", "Blech|Flachprofil|Winkelprofil|Rohr|Rundstab|Vierkant|Platte"),
            F("size", "Maße", "", hint="z. B. 2 mm, 20x2, Ø8"),
        ),
        (("{kind}",), ("{form}",), ("{size}",)),
    ),
    Type(
        "allgemein",
        GROUPS[7],
        "Sonstiges (freier Name)",
        "ART",
        (F("name", "Bezeichnung", "", hint="z. B. Zahnrad 20 Zähne"),),
        (("{name}",),),
    ),
)

BY_KEY = {t.key: t for t in TYPES}


def grouped() -> list[tuple[str, list[Type]]]:
    return [(g, [t for t in TYPES if t.group == g]) for g in GROUPS]


def name(t: Type, values: dict[str, str]) -> str:
    """Name aus den Vorlagen: pro Teil die erste Alternative, deren Felder alle ausgefüllt sind."""
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
) -> int:
    t = BY_KEY.get(type_key)
    if t is None:
        raise LagerError("Unbekannter Teile-Typ")
    clean = {f.key: values.get(f.key, "").strip() for f in t.fields}
    text = name(t, clean)
    if not text:
        raise LagerError(f"Bitte mindestens ein Feld für „{t.label}“ ausfüllen")
    code = (
        codes.new_item_code(conn)
        if t.cat == codes.ITEM_PREFIX
        else codes.reserve(conn, t.cat, 1)[0]
    )
    tags = " ".join(v.lower() for v in (t.label, *clean.values()) if v)
    item_id = repo.add_item(conn, container_id, text, qty=qty, code=code, tags=tags)
    if t.cmp:
        form = {
            f"spec_{k}": v
            for k, v in clean.items()
            if v and k in {f.key for f in materials.FIELDS["cmp"]}
        }
        form["spec_function"] = " ".join(p for p in (t.label, clean.get("kind", "")) if p)
        materials.save_specs(conn, item_id, "cmp", form)
    return item_id


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
        extra = next((f for f in t.fields[1:] if f.options), None)
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
    t = BY_KEY.get(type_key)
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
    if t.cmp:
        materials.save_specs(conn, item_id, "cmp", {"spec_function": f"{t.label} {art}".strip()})
    return item_id
