# Status

Stand: 2026-10-26

## Aktuell
- App „KP Lager“ läuft auf dem Windows-PC unter **https://lager.home.lan** (DNS in AdGuard auf 192.168.74.6 → 192.168.74.5). Start: `tools/serve.ps1` (443 HTTPS + 80 für `/ca.crt`).
- Neu: NORB16-Draufsicht mit Einsätzen (EIN-Codes), Schnelleingabe im Kasten, Etiketten-Warteschlange (XLSX/A8/A4 40×12), responsives Layout (Handy: untere Navigation, Desktop: Seitenleiste), Einstellungsregister (`app/prefs.py`).
- Bin-Generator `cad/norb_bins.py`: Rillen (Spitzbogen), Greifmulde R15, Innenrundungen, Etikettenablage. **Testdruck steht aus** (Passung, Rippenrichtung).
- Offen: Windows-Firewall eingehend 80/443 erlauben (Handy-Zugriff), Probedruck D30 + QR-Scan, Docker-Host für Dauerbetrieb.

## Session-Start (für autonome Umsetzung, Modell: Sonnet reicht)
> Lies CLAUDE.md und docs/STATUS.md. Setze den nächsten offenen Meilenstein um (eigener Branch), bis Tests/Lint/Typecheck grün sind. Hake ihn hier ab, pflege ARCHITECTURE/DECISIONS bei Bedarf, committe und merge nach main. Nicht zwischendurch nachfragen.

## Meilensteine
- [x] **M0 Setup**: Repo `C:\dev\sortiersystem`, uv, FastAPI-Skeleton, pytest/ruff/mypy, htmx vendored.
- [x] **M1 Datenmodell**: Behälter-Baum, Items, Protokoll (`001_init.sql`, `repo.py`).
- [x] **M2 Mobile UI**: `/c/{code}` (freier Code → Anlegen), Behälterseite mit Pfad, −/+ per htmx, Sortierkasten-Raster, Umlagern per „aufnehmen → Ziel scannen → hier ablegen“.
- [x] **M3 Suche**: FTS5 trigram + Umlaut-fähiges LIKE für Wörter < 3 Zeichen, Behälter nach Name/Code, Code im Suchfeld springt direkt.
- [x] **M4 QR-Etiketten**: `/labels` A4-Bögen (Standard 4×10 à 48,5×25,4 mm, anpassbar), Zähler „als gedruckt merken“.
- [x] **M5 Import/Export**: `/import` mit Vorschau (läuft auf DB-Kopie), Idempotenz, `slot` → Fach; `/export.json` voller Dump.
- [x] **M6 Deployment-Dateien**: ersetzt durch Docker Compose (siehe Aktuell).
- [x] **M7b Code-Schema & D30**: PRÄFIX-NNN, ART-Codes für Teile, XLSX-Export 40×12, Einstellungen.
- [x] **M7c Druckvorschau & A8**: editierbare Tabelle vor Export, A8-Bogen (A4 quer, 16 Stück).
- [x] **M7 Fotos**: Upload per Handykamera, EXIF-Drehung, 1600 px + Thumbnail, Löschen räumt Dateien auf.
- [x] **M8 Alltag**: Rückgängig + Verlauf, Favoriten, Zuletzt angesehen, PWA-Icon, Verliehen-Status, Mindestbestand/Einkaufsliste, Freie Plätze, Synonyme + Tippfehler-Suche, Schnelleingabe „3 Rollen Lötzinn“, Haiku-Prompt pro Behälter, Scan-Modus (Öffnen/Einräumen), Spracheingabe über externen Whisper (`LAGER_WHISPER_URL`), Docker + Backup-Modul.
- [x] **M9a NORB16 & Bins**: Kastenmodell, Draufsicht, Einsätze, Warteschlange, CAD-Generator.
- [x] **M9c Admin**: Einstellungen › Admin – Code-Zähler je Präfix setzen/zurücksetzen, einzelne Codes entfernen.
- [x] **M9b UX & Einstellungen**: responsives Layout, Toasts, Einstellungsregister, Backup-Knopf, HTTPS im LAN.
- [x] **M8b Spracheingabe** über KI-Gateway auf KP-DESKTOP (`http://127.0.0.1:8766`, Modell parakeet, wählbar); Diktat mit mehreren Teilen.
- [ ] **M9 Optional**: semantische Suche (lokale Embeddings), Claude-API- oder Ollama-Extraktion aus Foto+Transkript, Status „ausgeliehen“ für Werkzeug.

## Backlog 2026-10-27 (User-Wunschliste, Reihenfolge = Umsetzung)
- [x] **M10 Design Crimson Night Core**: Tokens (Nacht, Karmin, Schein …), Instrument Serif/Geist/Geist Mono, Material Symbols Rounded 300 über Rollen (`nav.home` …), alles lokal gebündelt (offline), keine Emoji. Theme konfigurierbar.
- [x] **M11 Datenmodell**: Typen als Liste mit Codes TYP-001 (mechanical, electronic, smart-home, TBD …, unterwegs neu anlegbar); Anzeigename + vollständiger Name; Modellnummer + Datenblatt (URL → PDF lokal, Such-Link); Flag „zu prüfen“ für KI-Einträge; Eingang „Zu sortieren“; Entnahmen; Projekte; API-Schlüssel.
- [x] **M12 Start & Verlauf**: „Zuletzt angesehen“ nur im Verlauf-Tab; Start = eine Eingabe für alles (Teil, Behälter, Typ), Abschnitte konfigurierbar.
- [x] **M13 Scan**: Entnehmen (Menge sofort runter, nach 7 Tagen automatisch bestätigt, am Teil stornierbar); Projekte: Teileliste per Scan systematisch einsammeln.
- [x] **M14 Etiketten**: Export immer XLSX; A4 als eigene Seite mit Auswahl aus allen etikettierten Teilen.
- [ ] **M15 Lokale KI** (Gateway Chat): Teil vollständig ausfüllen ohne Haiku; „An lokale KI senden“ neben jedem Prompt-Kopieren; kompakter Prompt für lokale Modelle inkl. dynamischer Typen; alle KI-Ergebnisse mit Flag „zu prüfen“ → Tab „Freigaben“ unter Mehr (freigeben/ändern).
- [ ] **M16 Sprach-Tab** in der unteren Leiste: langes Diktat + Dauer-Aufnahme Teil für Teil, getrennt durch „weiter“ oder Knopf → Einträge in „Zu sortieren“.
- [ ] **M17 API**: REST `/api/v1` (Suchen/Lesen offen, Schreiben nur mit Schlüssel), CLI `tools/lager_cli.py`, MCP-Server `tools/lager_mcp.py`.

## Offen / zu klären
- [x] DNS `lager.home.lan` → 192.168.74.5 (AdGuard auf kp-pi3).
- [ ] Firewall: eingehend TCP 80/443 (Profil Privat) freigeben – nur durch den Nutzer.

## Bekannte Probleme
- pytest-Warnung: Starlette empfiehlt `httpx2` statt `httpx` für TestClient. Harmlos; Wechsel erst nach Prüfung des Pakets.
- LXC: Debian 13 nehmen (Python 3.13); install.sh lässt uv sonst passendes Python laden.
- Raspberry Pi 2B: nur Notbetrieb, ungetestet.
