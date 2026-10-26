# Status

Stand: 2026-10-26

## Aktuell
- M0–M7 erledigt und in `main` (53 Tests grün, UI im Handy-Viewport geprüft).
- **Nächster Schritt: Deployment auf dem Proxmox-LXC** nach `deploy/README.md` (braucht Zugriff auf den Server → manuell oder in einer Session mit SSH-Zugang).
- Danach: Etiketten drucken, Erst-Inventur per Haiku-Chat (`docs/HAIKU_PROMPT.md`) → `/import`.

## Session-Start (für autonome Umsetzung, Modell: Sonnet reicht)
> Lies CLAUDE.md und docs/STATUS.md. Setze den nächsten offenen Meilenstein um (eigener Branch), bis Tests/Lint/Typecheck grün sind. Hake ihn hier ab, pflege ARCHITECTURE/DECISIONS bei Bedarf, committe und merge nach main. Nicht zwischendurch nachfragen.

## Meilensteine
- [x] **M0 Setup**: Repo `C:\dev\sortiersystem`, uv, FastAPI-Skeleton, pytest/ruff/mypy, htmx vendored.
- [x] **M1 Datenmodell**: Behälter-Baum, Items, Protokoll (`001_init.sql`, `repo.py`).
- [x] **M2 Mobile UI**: `/c/{code}` (freier Code → Anlegen), Behälterseite mit Pfad, −/+ per htmx, Sortierkasten-Raster, Umlagern per „aufnehmen → Ziel scannen → hier ablegen“.
- [x] **M3 Suche**: FTS5 trigram + Umlaut-fähiges LIKE für Wörter < 3 Zeichen, Behälter nach Name/Code, Code im Suchfeld springt direkt.
- [x] **M4 QR-Etiketten**: `/labels` A4-Bögen (Standard 4×10 à 48,5×25,4 mm, anpassbar), Zähler „als gedruckt merken“.
- [x] **M5 Import/Export**: `/import` mit Vorschau (läuft auf DB-Kopie), Idempotenz, `slot` → Fach; `/export.json` voller Dump.
- [x] **M6 Deployment-Dateien**: `deploy/` (install.sh, systemd, Caddy `tls internal` + `/ca.crt`, Backup-Timer). **Auf echtem Server noch nicht getestet.**
- [x] **M7 Fotos**: Upload per Handykamera, EXIF-Drehung, 1600 px + Thumbnail, Löschen räumt Dateien auf.
- [ ] **M8 Sprache (niedrige Prio)**: separater Dienst faster-whisper (`small`, int8, CPU), Aufnahme per MediaRecorder → Transkript ins Eingabefeld. Abschaltbar per Config. Erst sinnvoll, wenn HTTPS im LAN läuft (Mikrofon).
- [ ] **M9 Optional**: semantische Suche (lokale Embeddings), Claude-API- oder Ollama-Extraktion aus Foto+Transkript, Status „ausgeliehen“ für Werkzeug.

## Offen / zu klären
- [ ] **Hostname vor dem Etikettendruck festlegen** (steht in jedem QR): `lager.fritz.box` (Fritz!Box) oder `lager.home.arpa` (eigener DNS).
- [ ] Etikettenbogen: Standardmaß 48,5×25,4 mm (4×10) – bei anderem Bogen Maße im Formular anpassen, Probedruck auf Normalpapier.

## Bekannte Probleme
- pytest-Warnung: Starlette empfiehlt `httpx2` statt `httpx` für TestClient. Harmlos; Wechsel erst nach Prüfung des Pakets.
- LXC: Debian 13 nehmen (Python 3.13); install.sh lässt uv sonst passendes Python laden.
- Raspberry Pi 2B: nur Notbetrieb, ungetestet.
