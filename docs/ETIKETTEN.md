# Etiketten & Code-Schema

## Schema
`PRÄFIX-Nummer` – der Code sagt, **was** etwas ist, nie **wo** es steht (Umzug ändert kein Etikett).

Quelle: `app/kinds.py` (feste Arten, Namen DE/EN, Einstellung „Sprache der Namen“). Eigene Arten mit eigenem Präfix: Etiketten → Code-Schema oder Start „Neue Art …“.

| Gruppe | Präfix | Art (EN / DE) | Schlüssel |
|---|---|---|---|
| Standorte & Infrastruktur | RAU | Room / Raum | room |
| | REG | Shelf / Racking / Regal | shelf |
| | WBA | Workbench / Werkbank | workbench |
| | WAL | Wall / Pegboard / Lochwand | wall |
| | DRW | Drawer Unit / Schubladenelement | drawer |
| Behälter & Aufbewahrung | TBX | Tool Box / Werkzeugbox (Kistenberg Pro) | toolbox |
| | MCF | Machine Case / Maschinenkoffer | case |
| | MOD | Modular Box / Modulbox | module |
| | SOR | Sorting Box / Sortierkasten | sortingbox |
| | EUR | Eurobox | eurobox |
| | KIS | Crate / Large Box / Kiste | crate |
| | BOX | Box | box |
| | BIN | Bin / Insert / Einsatz | bin |
| Verbrauch & Rohmaterial | CNS | Consumables / Verbrauchsmaterial | consumables |
| | RAW | Raw Material / Rohmaterial | raw |
| | CBL | Cables & Wire / Kabel | cables |
| | CMP | Electronic Components / Elektronikbauteile | components |
| Sicherheit | PPE | Personal Protective Equipment / PSA | ppe |
| Gegenstände | ART | Article / Item (4 Stellen) | – |
| | TYP | Type – Name immer klein (makita, handwerkzeug) | – |

Ohne eigenen Code: `level` (Ebene), `compartment` (Fach). Alte Codes: STA → TBX, EIN → BIN (Migration 011).

- Fächer haben kein eigenes Etikett: jedes Teil im Fach bekommt sein ART-Etikett (QR + Name).
- Eingabe tolerant: `eur1`, `EUR001`, `Eur-001` → `EUR-001`.
- Zähler je Präfix: reservierte/gedruckte Codes werden nie doppelt vergeben, auch nach Löschen nicht.
- Unbekannten Code scannen → Anlegen-Formular mit passender Art (ART → neuer Gegenstand).
- Einstellung „Neue Teile bekommen automatisch einen ART-Code“ (Standard an) unter `/settings`.

## QR-Inhalt
`HTTP(S)://LAGER.HOME.LAN/C/EUR-001` – komplett groß geschrieben → QR-Alphanumerik-Modus, Version 2 (25×25 Module) statt 3. Bei 10 mm QR auf dem D30 (203 dpi) ≈ 3 Druckpunkte pro Modul. **Probedruck mit Handy testen.**

## D30 (40×12 mm) einrichten – einmalig
1. In der App „Etiketten“ eine XLSX laden (Spalten: `Code | QR | Text`).
2. In der D30-App neue Vorlage 40×12 mm, Excel/Batch-Import, XLSX wählen.
3. Elemente anlegen und Spalten zuordnen:
   - QR-Code links, ca. 10×10 mm ← Spalte **QR**
   - Text oben rechts, fett ← **Code** (bei Behälter-Etiketten) bzw. **Text** (Name bei Teilen)
4. Vorlage speichern; danach nur noch neue XLSX importieren und drucken.

## Abläufe
Jede Auswahl öffnet zuerst die **Vorschau-Tabelle** (Code | Text | Zusatz). Texte lassen sich dort ändern
(rot = zu lang für 40×12, wird im XLSX gekürzt). Optional „Geänderte Texte auch als Namen im Lager speichern“.
Export immer als **XLSX für den D30**. Papierdruck separat unter **Etiketten › A4-Druck**: beliebige Etiketten auswählen, als 40×12-Bogen (110/Seite) oder A8 (16/Seite).

- **Neue Boxen:** `Etiketten › Neue Codes auf Vorrat` (z. B. 20× EUR) → Vorschau (Text z. B. „Elektronik“) → Export → aufkleben → beim ersten Scan anlegen. Codes werden erst beim Export reserviert.
- **Sortierkasten komplett:** Kastenseite › „Etiketten aller Teile drucken“ → ein Etikett pro Teil, fehlende ART-Codes werden vergeben.
- **Alles Neue seit dem letzten Druck:** `Etiketten › Noch nicht gedruckt`.
- **Einzelnes Teil:** Teileseite › „Etikett drucken“ (bzw. „Etikett vergeben“).
- Export zählt als gedruckt. Erneut drucken: Teil- oder Kasten-Etiketten nochmal öffnen.

## A8-Etiketten (Normaldrucker)
A4 **quer**, 4×4 = 16 Etiketten à 74×52 mm (A8 quer), dünne graue Schnittlinien.
Aufbau je Etikett: **QR links** (40 mm), rechts **Name** (bis 5 Zeilen) + Zusatz, unten **Code**.
Drucken mit Skalierung 100 %, Ränder „keine“. Gut für Euroboxen, Kisten, Regale (aus Distanz lesbar).
