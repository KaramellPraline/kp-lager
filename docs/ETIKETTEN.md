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

## D30 (40×12 mm)
Gedruckt wird direkt (PC-Agent per MQTT, Bluetooth oder `/labels/img/<CODE>.png`), nicht mehr über
XLSX – der XLSX-Export ist seit 1.1.0 entfernt. Siehe `docs/DIREKTDRUCK.md`, `docs/PRINT_MQTT.md`.

## Standard-Etikett und Layout je Typ
Jeder Katalogtyp druckt standardmäßig **dreizeilig** (QR links): Typ + Spezifikation · Maße · Code,
z. B. „Heat-Set Insert M3“ / „3 x 4.2mm“ / „CNS-002“. Vorrang: im Designer gespeichertes Layout
(`/etiketten/typ/<Typ>`) > eigene Haupt-/Zusatzzeile des Typs > dieses Standardlayout
(`catalog.default_label_layout`, `Type.label_lines`). Im Anlegen-Formular zeigt eine Live-Vorschau das
Etikett; Antippen öffnet den Designer und Speichern bringt mit allen Eingaben zurück.

## Abläufe
Jede Auswahl öffnet zuerst die **Vorschau-Tabelle** (Code | Text | Zusatz). Texte lassen sich dort ändern
(rot = zu lang für 40×12). Optional „Geänderte Texte auch als Namen im Lager speichern“.
Ziele: **Auf D30 drucken**, **In Warteschlange** (D30) oder **In A4-Warteschlange** (`docs/A4.md`).

- **Neue Boxen:** `Drucken › Neue Codes auf Vorrat` (z. B. 20× EUR) → Vorschau (Text z. B. „Elektronik“) → drucken → aufkleben → beim ersten Scan anlegen. Codes werden erst beim Drucken reserviert.
- **Sortierkasten komplett:** Kastenseite › „Etiketten aller Teile drucken“ → ein Etikett pro Teil, fehlende ART-Codes werden vergeben.
- **Alles Neue seit dem letzten Druck:** `Drucken › Noch nicht gedruckt`.
- **Einzelnes Teil:** Druck-Symbol an Teil/Behälter (sofort, sonst Warteschlange).
- **Druck scheitert** (Agent/MQTT/D30 offline): die Etiketten werden automatisch in die Warteschlange gelegt, die Meldung nennt den Grund.
- **Satz:** Varianten-Reihe und „Alle Etiketten drucken (Satz)“ drucken mehrere Etiketten in einem Rutsch.

## A4 (Seiten-, Box-, Inhaltsetiketten)
Eigene Etikettentypen, Warteschlange, automatische Anordnung und Netzwerkdruck: `docs/A4.md`.
