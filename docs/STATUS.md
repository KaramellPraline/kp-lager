# Status

Stand: 2026-10-26

## Aktuell
- M0, M1 erledigt (in main). Nächster Schritt: M2.

## Session-Start (für autonome Umsetzung, Modell: Sonnet reicht)
> Lies CLAUDE.md und docs/STATUS.md. Setze den nächsten offenen Meilenstein um (eigener Branch), bis Tests/Lint/Typecheck grün sind. Hake ihn hier ab, pflege ARCHITECTURE/DECISIONS bei Bedarf, committe.

## Meilensteine (je eine Session, Abnahme = genannte Tests grün)
- [x] **M0 Setup**: Code-Repo nach `C:\dev\sortiersystem` verschieben (nicht in Google Drive!), `git init`, uv-Projekt, FastAPI-Skeleton mit `/health`, pytest/ruff/mypy konfiguriert, htmx.min.js nach `app/static/` vendored. Test: `/health` → 200.
- [x] **M1 Datenmodell**: Migrations-Runner + `001_init.sql` (Tabellen laut ARCHITECTURE), Repository-Funktionen für Behälter/Items/Events. Tests: anlegen, verschachteln, Pfad (Raum › Regal › Box › Fach), Entnahme erzeugt Event, Menge nie < 0.
- [ ] **M2 Mobile UI**: `/c/{code}` zeigt Pfad, Unterbehälter, Inhalt mit −/+; Item hinzufügen (ein Feld, Menge optional); Behälter umziehen („in Behälter X“); unbekannter Code → „Neuen Behälter anlegen“. Sortierkasten: Fach-Raster (z. B. 6×8) antippbar. Tests via TestClient.
- [ ] **M3 Suche**: FTS5 mit `trigram`-Tokenizer (findet „schraub“ in „Holzschrauben“), Suchfeld auf jeder Seite, Treffer mit Pfad + Fach + Menge. Tests: Teilwort, Umlaute, Tag-Treffer.
- [ ] **M4 QR-Etiketten**: Bögen mit fortlaufenden, noch freien Codes drucken (`/labels?from=1&count=48`, A4, Etikettengröße konfigurierbar), QR als SVG via segno, URL = `BASE_URL/c/{code}`. Test: SVG enthält korrekte URL.
- [ ] **M5 Import/Export**: `/import` Textfeld für JSON aus dem Haiku-Chat (Format in `docs/HAIKU_PROMPT.md`), Vorschau → Übernehmen; Export als JSON (= Backup-Format). Tests: Validierung, Idempotenz (gleicher Import doppelt = keine Dubletten).
- [ ] **M6 Deployment**: Debian-12-LXC auf Proxmox, systemd-Unit, Caddy mit `tls internal` (Root-CA aufs Handy), DNS-Name im Router (z. B. `lager.home`), nächtliches `sqlite3 .backup` + Fotos → NAS/Drive. Anleitung in `deploy/README.md`.
- [ ] **M7 Fotos**: Foto pro Behälter/Item (Kamera via `<input capture>`), Thumbnails mit Pillow, Ablage `data/photos/`.
- [ ] **M8 Sprache (niedrige Prio)**: separater Dienst faster-whisper (`small`, int8, CPU), Aufnahme per MediaRecorder → Transkript landet im Eingabefeld. Abschaltbar per Config.
- [ ] **M9 Optional**: semantische Suche (lokale Embeddings), Claude-API- oder Ollama-Extraktion aus Foto+Transkript.

## Offen / zu klären
- [ ] Etikettenformat/Drucker (A4-Bogen vs. Labeldrucker) – vor M4 klären.
- [ ] Domainname im LAN (Router-DNS) – vor M6 klären.

## Bekannte Probleme
- pytest-Warnung: Starlette empfiehlt `httpx2` statt `httpx` für TestClient. Harmlos; Wechsel erst nach Prüfung des Pakets.
- Server: Debian 13 (Python 3.13) als LXC-Basis nehmen; Debian 12 hat nur 3.11 (sonst Python via uv installieren).
