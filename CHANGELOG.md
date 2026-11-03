# Änderungen

Format: je Version ein Abschnitt `## [x.y.z] – Datum`. Der Abschnitt der Release-Version wird als
Text des GitHub-Releases übernommen (`tools/release.py notes`).

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
- Windows: Client (Fenster + D30-PC-Bridge) und Server (Debug) als getrennte Installer, `tools/dev.ps1`.
- Entnehmen am Teil mit Schnellauswahl der Menge.

### Entfernt
- Alle KI-Bausteine (Spracheingabe/Whisper, lokale KI, Foto-Erkennung, KI-Support, Freigaben, Haiku-Prompt).

## [0.1.0] – 2026-10-26

- Erste lauffähige Version: Behälter-Baum, Teile, QR-Etiketten, Suche, Fotos, Import/Export, Docker-Deployment.
