# Status

Stand: 2026-10-26

## Aktuell
- App „KP Lager“, alle Funktionen in `main`, 86 Tests grün. Dev-Server auf dem Windows-PC (http://192.168.74.5:8000), QR-Codes zeigen auf `https://lager.home.lan`.
- Hosting: Docker-Compose fertig (`deploy/`), **noch nicht gebaut/getestet, Host offen** (kp-pi3 verworfen 2026-10-26).
- DNS: AdGuard Home lief auf altem Pi 192.168.74.90 – derzeit offline. Eintrag `lager.home.lan` → Docker-Host fehlt noch.
- Offen: Probedruck D30 40×12 + A8 testen (QR-Scan mit Handy).

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
- [ ] **M8b Whisper-Dienst** auf stärkerem Host (Proxmox) starten und URL setzen.
- [ ] **M9 Optional**: semantische Suche (lokale Embeddings), Claude-API- oder Ollama-Extraktion aus Foto+Transkript, Status „ausgeliehen“ für Werkzeug.

## Offen / zu klären
- [ ] DNS-Eintrag `lager.home.lan` → Container-IP im Router anlegen (Hostname festgelegt, steht in jedem QR).
- [ ] Etikettenbogen: Standardmaß 48,5×25,4 mm (4×10) – bei anderem Bogen Maße im Formular anpassen, Probedruck auf Normalpapier.

## Bekannte Probleme
- pytest-Warnung: Starlette empfiehlt `httpx2` statt `httpx` für TestClient. Harmlos; Wechsel erst nach Prüfung des Pakets.
- LXC: Debian 13 nehmen (Python 3.13); install.sh lässt uv sonst passendes Python laden.
- Raspberry Pi 2B: nur Notbetrieb, ungetestet.
