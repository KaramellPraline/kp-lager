# Verbrauchsmaterial: Filament & Harz (Workflow, seit 1.1.0)

Spulen und Flaschen werden über **Hinzufügen → Teile → Filament & Harz** angelegt. Jede Spule/Flasche
ist ein Einzelteil (FIL-/RES-Code, eigenes Etikett), die Restmenge wird per Wägung geführt.

## Felder Filament-Spule
| Feld | Hinweis |
|---|---|
| Hersteller | Auswahl + freie Eingabe; neue Hersteller werden gemerkt (siehe unten) |
| **Kunststoff** + Anteil % | z. B. PA12, 80 % |
| **Zusatz** + Anteil % | z. B. Carbonfaser 20 % (Glasfaser, Kevlar, Holz, Metall …) |
| Farbe, Durchmesser (mm), Gewicht je Spule (kg) | |
| **Spulentyp** | Pappe, Plastik, Mehrweg, Masterspool, Refill, Metall |
| **Spulenleergewicht** (g) | Basis der Restmengen-Wägung |
| **Preis** (€) | landet in `item.price` (Wert der Teile, Einkauf) |

Aus Kunststoff und Zusatz entsteht der **Werkstoff** („PA12 80% + CF 20%“; Glasfaser → GF,
Carbonfaser → CF) und damit der Name: „Hersteller Werkstoff Farbe“. Das Gewicht wird im Datenblatt in
Gramm gespeichert.

## Felder UV-Harz-Flasche
Hersteller, Harztyp, Farbe, Inhalt (250/500/1000 ml), **Leerflasche** (g), **Preis**.

## Klassen (Presets)
In der obersten Reihe stehen die Klassen als Chips (PLA, PLA+, PETG, ABS, ASA, TPU, PA12-CF, PETG-CF,
PLA-CF, PA6-GF; Harz: Standard, ABS-like, Tough, Flexibel, Wasserwaschbar). Ein Klick füllt Kunststoff,
Zusatz, Anteile, Durchmesser, Gewicht, Spulentyp und Leergewicht vor – danach nur noch Hersteller,
Farbe und Preis ergänzen.

**Preset-Ersteller:** Felder ausfüllen → „+ Preset“ → Name → Speichern. Gespeichert wird alles, was
ausgefüllt ist (auch Hersteller, Preis). Löschen über dieselbe Fläche („Name ×“). Presets liegen in der
Tabelle `preset` (Migration 027) und sind für **jeden** Typ nutzbar (Schlüssel = Typ).

**Hersteller:** Wird beim Anlegen oder Preset-Speichern ein Hersteller manuell eingetragen, der noch
nicht in der Liste steht, merkt ihn das System (`setting brands_<typ>`) und bietet ihn künftig als Chip
und in der Auswahl an – auch im Preset-Ersteller.

## Ablauf (Standard)
1. Hinzufügen → Typ „Filament-Spule“ (oder „UV-Harz-Flasche“).
2. Klasse antippen → Hersteller, Farbe, Preis eintragen (ggf. „merken“-Haken beim Hersteller setzen).
3. Wohin? wählen (Standard: Zu sortieren / zuletzt benutzter Ort) → Anlegen.
4. Etikett: je nach Druckmodus sofort (D30), Warteschlange oder gar nicht.
5. Mehrere gleiche Spulen: **Varianten-Reihe** (z. B. Farben) legt sie in einem Schritt an.
6. Im Betrieb: wiegen (Teileseite) → Restmenge; Entnahme/Nachkauf wie bei allen Teilen, Einkaufsliste
   über Mindestbestand.

## Zahlen
Dezimalzahlen werden systemweit mit **Punkt** geschrieben: Tippt man ein Komma zwischen Ziffern
(„1,75“), wird es sofort zu „1.75“ (`app.js`); der Server normalisiert zusätzlich (`catalog.number`).
Ausnahme: das Feld „Varianten-Reihe“ (Liste mit Komma).
