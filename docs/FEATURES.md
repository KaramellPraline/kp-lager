# Funktionen im Detail

## Anlegen

- **Schnelleingabe (Startseite):** Tabs Teil · Behälter · Alle · Katalog. „3 Rollen Lötzinn und 50 M3 Muttern“ wird zerlegt.
  Kategorien und Behälterarten stehen in einer 3×3-Matrix (seitlich scrollbar), zuletzt benutzte vorn.
  Kabel (CBL) und Netzteile (PSU) haben eigene Felder, jedes Stück bekommt ein Etikett. Filament (FIL) und UV-Harz (RES)
  haben Dropdowns (Hersteller, Werkstoff, Farbe, Durchmesser, Gewicht), die mit dem Bestand wachsen.
- **Katalog (`/neu`):** ~55 Teile-Typen in 8 Gruppen (Schrauben & Befestigung, Klebstoff & Verbrauch, Mechanik & Pneumatik,
  Kabel & Elektrik, Elektronik, Werkzeug, 3D-Druck & Laser, Material & Holz). Gruppen einklappbar (Zustand und Scrollposition
  bleiben beim Wechsel erhalten). Felder per Chip oder Eingabe, Live-Namensvorschau, danach bleibt der Typ mit leeren Feldern offen.
- **Einsatz-Assistent (`/neu/bin`):** Sortierkasten wählen → freie Zelle, Breite X × Tiefe Y, Anzahl Fächer → je Fach Art,
  Variante, Menge. Optional Inhalts- und QR-Etikett vormerken bzw. direkt drucken.
- **Behälter:** Art als Kachel (inkl. Maschine `MAS`, Filamenttrockner `TRO`), Größe aus vorhandenen Boxen/Euro-Normen, „Luftdicht“.
- **Foto, Import:** Foto per Handykamera am Teil/Behälter, JSON-Import/-Export. Keine KI-Funktionen.

## Übersicht und Suche

- Startseite und `/baum`: aufklappbarer Baum (Zweige laden beim Aufklappen), ab dem 10. Eintrag „Mehr anzeigen“.
- Suche (`/suche`): Wortstämme, Synonyme, Tippfehler, Tag-Filter; Code im Suchfeld springt direkt.
- Freie Plätze, Verlauf mit Rückgängig, Verliehen, Einkaufsliste (Mindestbestand, Bestellt/Eingetroffen), Lagerwert je Behälter.

## Etiketten und Drucken

- Code-Schema `PRÄFIX-NNN`; QR-Inhalt in Großbuchstaben (`HTTPS://LAGER.HOME.LAN/C/EUR-001`).
- Etikett-Bild 40×12 mm (320×96 px): QR links, Name (automatische Schriftgröße, einzeilig), ID groß, 1 mm Rand, kein Rahmen.
- Druckvorschau: „Auf D30 drucken“, „In Warteschlange“, „In A4-Warteschlange“ (kein XLSX mehr).
- **A4** (`docs/A4.md`): Seitenetiketten für Einsätze (alle Fächer), Box-Label mit abgerundetem Rahmen und Maßen, Inhaltsetiketten, Rot möglich; Warteschlange, automatische Anordnung, Druck erst nach Bestätigung per IPP.
- **Anlegen** (`docs/VERBRAUCH.md`): Live-Etikett, Klassen/Presets (Filament, Harz), Varianten-Reihe, Pflichtfelder zuerst, „merken“, Komma→Punkt.
- **Einsätze** (`docs/BINS.md`): Drag & Drop in der Draufsicht, Druck-Parameter, Bin-Druckdatei `bins.json`.
- **D30-Direktdruck:** Checkbox beim Eintragen (leuchtet bei erreichbarem Drucker), Knopf am Teil solange das Etikett offen ist.
  Weg: Bluetooth-Seriell (COM) zuerst, sonst BLE. Details: `docs/DIREKTDRUCK.md`.

## 3D-Druck und Material

- Filament/Harz mit Datenblatt, Restmenge per Wägung, Haltbarkeit/geöffnet-Datum, Einkaufsliste.
- **Trockner:** Programme je Material, Verlauf je Spule. Ablauf per Scan: Trockner-Etikett scannen → 10 Minuten Modus →
  Filament-Etikett(e) scannen = mit Datum und Uhrzeit als getrocknet gespeichert (Seite `/trockner/scan/<id>`).
- **Slicer-Import:** G-Code/3MF aus Creality Print, Orca, Cura → Verbrauch pro Spule buchen.

## Sortierkästen (NORB16)

Draufsicht mit Einsätzen, Schnelleingabe im Kasten, Inhaltsetiketten, Bin-Generator (`cad/norb_bins.py`, Spezifikation in `docs/BIN_SPEC.md`).

## Betrieb

Tägliches Backup, Statusseite (`/status`), Massenbearbeitung (`/auswahl`), Einstellungen (`/settings`), REST/CLI/MCP.
- Einsätze (BIN) mit Rastermaß und Teilung unter Hinzufügen › Behälter anlegen, im Sortierkasten als vorhandene Einsätze wählbar (M53, `docs/BINS.md`).
