# Änderungen

Format: je Version ein Abschnitt `## [x.y.z] – Datum`. Der Abschnitt der Release-Version wird als
Text des GitHub-Releases übernommen (`tools/release.py notes`).

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
