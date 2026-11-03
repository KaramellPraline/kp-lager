# KP Lager (Repo: sortiersystem)

Zweck: Selbst gehostetes Lagersystem; QR-Code auf Behälter → Handy-Browser zeigt Inhalt, Einlagern/Entnehmen/Suchen im LAN.
Stack: Python ≥3.12, FastAPI, Jinja2 + HTMX (vendored, kein JS-Build), SQLite (stdlib `sqlite3`, kein ORM, FTS5), segno (QR), Pillow, uv. Betrieb: Docker Compose (App + Caddy HTTPS), Host noch offen.

## Befehle
- Run (dev): `uv run uvicorn app.main:app --reload --port 8000` (Daten in `./data`)
- Run (LAN mit HTTPS, Windows): `powershell -File tools\serve.ps1` → https://lager.home.lan (Zertifikat: `tools/devcert.py`)
- Bins (3D-Druck): `uv run --group cad python cad/norb_bins.py 2x1 --div 3x1` (siehe `docs/NORB16.md`)
- Test: `uv run python -m pytest -q --ignore=tests/test_cad.py` (CAD-Tests: `uv sync --group cad`, dann `tests/test_cad.py`)
- Lint/Typecheck: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
- API/CLI/MCP: REST `/api/v1` (Lesen offen, Schreiben mit Schlüssel aus Einstellungen → Admin); `uv run python tools/lager_cli.py suche lötzinn`; MCP: `uv run --group mcp python tools/lager_mcp.py` (Vorlage `docs/mcp.example.json`)
- Deploy: `cd deploy && docker compose up -d --build` (siehe `deploy/README.md`)
- Backup: `python -m app.backup [ziel] [tage]`

## Secrets
- `LAGER_API_KEY` (nur lokal für CLI/MCP-Schreibzugriff, nie committen). KI-API ist bewusst nicht eingebunden (siehe DECISIONS).

## Regeln
- Arbeit in Meilensteinen aus `docs/STATUS.md`; pro Meilenstein ein Branch `feat/mX-…`, Abnahmekriterien = Tests.
- Kern muss ohne KI-Komponenten laufen (Whisper/Embeddings optional, per Config abschaltbar).
- Mobile first: jede Seite per Daumen bedienbar, max. 2 Taps für Entnehmen/Einlagern.
- Schema-Änderungen nur als nummerierte SQL-Dateien in `app/migrations/`.
- Keine externen CDNs (läuft offline im LAN).

Neu (2026-11): Katalog `/neu` (`app/catalog.py`), Einsatz-Assistent `/neu/bin`, Baum `/baum`, D30-Direktdruck (`app/d30.py`, Env `LAGER_D30*`), Trockner-Scan, Filament/Harz-Dropdowns (`app/choices.py`).
Cloud/CI: Hardware (D30-Bluetooth, lokale KI) ist nur gemockt testbar; Rest läuft überall. Einstieg: `docs/DEVELOPMENT.md`.

Mehr: `README.md`, `docs/DEVELOPMENT.md`, `docs/CONFIG.md`, `docs/DEPLOYMENT.md`, `docs/FEATURES.md`, `docs/STATUS.md` (Stand + Meilensteine), `docs/ARCHITECTURE.md` (Datenmodell), `docs/DECISIONS.md`, `docs/HAIKU_PROMPT.md` (Erst-Inventur per Chat), `docs/ETIKETTEN.md` (Code-Schema, D30)
