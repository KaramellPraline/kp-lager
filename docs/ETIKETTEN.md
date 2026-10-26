# Etiketten & Code-Schema

## Schema
`PRÄFIX-Nummer` – der Code sagt, **was** etwas ist, nie **wo** es steht (Umzug ändert kein Etikett).

| Präfix | Art | Stellen | Beispiel |
|---|---|---|---|
| RAU | Raum | 3 | RAU-001 |
| REG | Regal | 3 | REG-001 |
| STA | Stellplatz / Kistenberg | 3 | STA-001 |
| EUR | Eurobox | 3 | EUR-001 |
| KIS | Kiste / Box / Sonstiges | 3 | KIS-001 |
| SOR | Sortierkasten | 3 | SOR-001 |
| ART | Gegenstand (auch Teile in Fächern) | 4 | ART-0001 |

- Fächer haben kein eigenes Etikett: jedes Teil im Fach bekommt sein ART-Etikett (QR + Name).
- Eingabe tolerant: `eur1`, `EUR001`, `Eur-001` → `EUR-001`.
- Zähler je Präfix: reservierte/gedruckte Codes werden nie doppelt vergeben, auch nach Löschen nicht.
- Unbekannten Code scannen → Anlegen-Formular mit passender Art (ART → neuer Gegenstand).
- Einstellung „Neue Teile bekommen automatisch einen ART-Code“ (Standard an) unter `/settings`.

## QR-Inhalt
`HTTP(S)://LAGER.HOME.LAN/C/EUR-001` – komplett groß geschrieben → QR-Alphanumerik-Modus, Version 2 (25×25 Module) statt 3. Bei 10 mm QR auf dem D30 (203 dpi) ≈ 3 Druckpunkte pro Modul. **Probedruck mit Handy testen.**

## D30 (40×12 mm) einrichten – einmalig
1. In der App „Etiketten“ eine XLSX laden (Spalten: `Code | QR | Text | Zusatz`).
2. In der D30-App neue Vorlage 40×12 mm, Excel/Batch-Import, XLSX wählen.
3. Elemente anlegen und Spalten zuordnen:
   - QR-Code links, ca. 10×10 mm ← Spalte **QR**
   - Text oben rechts, fett ← **Code** (bei Behälter-Etiketten) bzw. **Text** (Name bei Teilen)
   - Text unten rechts, klein ← **Text** oder **Zusatz** (Fach, z. B. „B3“) – optional
4. Vorlage speichern; danach nur noch neue XLSX importieren und drucken.

## Abläufe
- **Neue Boxen:** `Etiketten › Neue Codes auf Vorrat` (z. B. 20× EUR) → XLSX → drucken → aufkleben → beim ersten Scan anlegen.
- **Sortierkasten komplett:** Kastenseite › „Etiketten aller Teile (XLSX)“ → ein Etikett pro Teil, fehlende ART-Codes werden vergeben.
- **Alles Neue seit dem letzten Druck:** `Etiketten › Noch nicht gedruckt` → XLSX.
- **Einzelnes Teil:** Teileseite › „Etikett (XLSX)“ (bzw. „Etikett vergeben“).
- Herunterladen zählt als gedruckt. Erneut drucken: Teil- oder Kastenexport nochmal laden.
- Alternative ohne D30: A4-Bogen (`/labels/sheet?prefix=EUR`).
