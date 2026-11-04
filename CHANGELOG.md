# Änderungen

Format: je Version ein Abschnitt `## [x.y.z] – Datum`. Der Abschnitt der Release-Version wird als
Text des GitHub-Releases übernommen (`tools/release.py notes`).

## [0.7.0] – 2026-11-04

### Neu
- Katalog: Filament-Spule, UV-Harz-Flasche (250/500/1000 ml), Steckernetzteil, Kabel mit Steckern, Werkzeug, PPE, Norb16-Bin; Menü „Kabel & Material“ entfällt.
- Mehr Kartenarten (Eigenschaften, Checkliste, Links); Notiz/Datenblatt-Link schon beim Anlegen.
- Admin: Nummernvergabe nach Gruppen mit Filter.
- Einsatz-Assistent: Standardgrößen 1x1/2x1/2x2/3x1/4x1, „noch nicht gedruckt“.

## [0.6.0] – 2026-11-04

### Neu
- Etiketten-Layout: Vorlagen („Alles“, Standard, Nur Name) und „Für alle Typen übernehmen“.
- Druckmodus-Menü beim Anlegen: Aus · Einzeln (sofort 40x12) · Sammeln (Warteschlange).
- Behälter-Leergewicht (Bearbeiten-Block am Behälter).
- 17 weitere Sortierkasten-Raster (insgesamt 18 Modelle).
- Druck-Agent (eigenes Repo): Symbolbibliothek für Homelab/DIY.

## [0.5.0] – 2026-11-04

### Neu
- Katalog: Favoriten (Stern, je Kategorie oben), Sprungleiste, zehn neue Typen (Gridfinity, Set/Sortiment, Kabel u. a.), automatische Tags, „Kein eigenes Etikett“, Ziel-Auswahl mit Zu-sortieren-Knopf.
- Felder: Insert (Außendurchmesser), Scheibe (Dicke, Außendurchmesser); Netzwerk- und Netzteil-Typen im Katalog; Etikettenfelder frei wählbar; Etikett-Layout-Vorschau.
- Behälter/Teil: Icon-Leiste (Drucken, Foto, Umlagern, Bearbeiten), mitlaufende Namenszeile, Rückgängig/Wiederholen in der Kopfzeile.
- Kiste drehen in der Draufsicht; Größe „x = lange Seite“.
- Druck per MQTT (Druck-Agent im eigenen Repo `kp-print-agent`), Druckverlauf mit Wiederholung/Batch, Regel „neue Teile automatisch drucken“.
- Gesamtarchiv-Export (Daten, Fotos, Einstellungen); Einstellungen im JSON-Export und in der Wiederherstellung.

### Geändert
- Kein Auto-Fokus mehr beim Typwechsel; Eingabefelder bleiben mit Handy-Tastatur sichtbar.
- Kategorien CNS/RAW/CMP nicht mehr als Kacheln; Tab „Kabel & Material“ entfällt (Filament/Harz per Link im Katalog).
- „Teil eintragen“ und „Darin anlegen“ auf der Behälterseite entfernt (Anlegen nur unter Hinzufügen).

## [0.4.0] – 2026-11-04

### Neu
- QR-Codes enthalten immer `https://lager.home.lan` (nie localhost oder eine IP).
- Windows nur noch als Client – der Server läuft ausschließlich als Docker-Container.
- Docker-Übergabe `deploy/handoff/`: drei Dateien und eine Kurzanleitung genügen für den Betrieb.
- Etiketten-Layout je Typ: Felder auf dem D30-Etikett anordnen (QR-Position, bis 4 Zeilen, Höhe, Ausrichtung), Schrift skaliert automatisch in jedes Feld, Live-Vorschau.
- Vollexport (Mehr › Export) lässt sich unter Mehr › Import als Datei wiederherstellen: Behälter/Teile werden über Codes zusammengeführt, fehlende Codes und die Zähler dynamisch gesetzt, Teile automatisch typisiert.

## [0.3.0] – 2026-11-04

### Neu
- Android-App als APK (KP-Lager-0.3.0.apk): eigenes Fenster, Server-Adresse einstellbar, QR-Scan mit Kamera, Foto-Upload, Downloads, offline über den Service Worker.
- Typen am Teil mit Datenblatt, Sortiment nach Typ, Variantenraster für alle Arten, Dublettenwarnung, eigene Typen, Altbestand-Zuordnung.
- Standard-Mindestbestand je Typ, Platz-Vorschlag beim Anlegen, Zählen per Waage, Ablauf-Erinnerung.
- Projekt-Reservierung; Einkauf aus CSV, Rechnungstext oder PDF übernehmen.
- Etikettenvorlagen je Typ, Sammeldruck je Box, Schnellaktionsmenü an Teilen.
- Installierbare Offline-App (Android), Home-Assistant-Sensor.

## [0.2.0] – 2026-11-03

### Neu
- Hinzufügen-Tab mit Reitern Teile · Behälter · Kabel & Material · Einsatz; merkt den letzten Reiter.
- Startseite als Bestandsbrowser (Orte / Baum) mit Suche, Aufgaben-Karten und Kennzahlen; „Mehr“ gruppiert.
- Stücklisten-Abgleich im Projekt, Einkäufe und Lieferanten, Notiz- und Pinout-Karten, Inventur.
- Externes Backup (Ordner/NAS) zusätzlich zum täglichen Backup.
- API mit Lese- und Schreib-Schlüsseln, Teile/Behälter bearbeiten, Projekte planen (`docs/API.md`); MCP mit 34 Werkzeugen.
- Windows: Client-Installer (Fenster + D30-PC-Bridge).
- Entnehmen am Teil mit Schnellauswahl der Menge.

### Entfernt
- Alle KI-Bausteine (Spracheingabe/Whisper, lokale KI, Foto-Erkennung, KI-Support, Freigaben, Haiku-Prompt).

## [0.1.0] – 2026-10-26

- Erste lauffähige Version: Behälter-Baum, Teile, QR-Etiketten, Suche, Fotos, Import/Export, Docker-Deployment.
