# KP Lager (Repo: sortiersystem)

Zweck: Selbst gehostetes Lagersystem; QR-Code auf Behälter → Handy-Browser zeigt Inhalt, Einlagern/Entnehmen/Suchen im LAN.
Stack: Python ≥3.12, FastAPI, Jinja2 + HTMX (vendored, kein JS-Build), SQLite (stdlib `sqlite3`, kein ORM, FTS5), segno (QR), Pillow, uv. Betrieb: Docker Compose (App + Caddy HTTPS), Host noch offen.

## Befehle
- Run (dev): `uv run uvicorn app.main:app --reload --port 8000` (Daten in `./data`)
- Run (LAN mit HTTPS, Windows): `powershell -File tools\serve.ps1` → https://lager.home.lan (Zertifikat: `tools/devcert.py`)
- Bins (3D-Druck): `uv run --group cad python cad/norb_bins.py 2x1 --div 3x1` (siehe `docs/NORB16.md`)
- Test: `uv run python -m pytest -q --ignore=tests/test_cad.py` (CAD-Tests: `uv sync --group cad`, dann `tests/test_cad.py`)
- Lint/Typecheck: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
- API/CLI/MCP: REST `/api/v1` (Lesen offen oder per Einstellung nur mit Schlüssel, Schreiben mit Schreib-Schlüssel aus Einstellungen → Admin, siehe `docs/API.md`); `uv run python tools/lager_cli.py suche lötzinn`; MCP: `uv run --group mcp python tools/lager_mcp.py` (Vorlage `docs/mcp.example.json`)
- Deploy: `cd deploy && docker compose up -d --build` (siehe `deploy/README.md`); Windows: `tools\dev.ps1` (Debug), Installer `windows/build.ps1` (siehe `docs/WINDOWS.md`)
- Backup: `python -m app.backup [ziel] [tage]`
- Release: `uv run python tools/release.py bump X.Y.Z`, CHANGELOG.md ausfüllen, Tag `vX.Y.Z` pushen (siehe `docs/RELEASE.md`, Installation `docs/INSTALL.md`)

## Secrets
- `LAGER_API_KEY` (nur lokal für CLI/MCP-Schreibzugriff, nie committen). Das System enthält keine KI-Bausteine (seit 2026-11-03, siehe DECISIONS).

## Regeln
- Arbeit in Meilensteinen aus `docs/STATUS.md`; pro Meilenstein ein Branch `feat/mX-…`, Abnahmekriterien = Tests.
- Keine KI-Komponenten (kein Whisper/LLM/Vision/Embeddings); alles läuft rein regelbasiert.
- Start (`/`) ist nur Bestandsbrowser; Anlegen immer im Tab „Hinzufügen“ (`/neu`: Teile · Behälter · Kabel & Material · Einsatz).
- Mobile first: jede Seite per Daumen bedienbar, max. 2 Taps für Entnehmen/Einlagern.
- Schema-Änderungen nur als nummerierte SQL-Dateien in `app/migrations/`.
- Keine externen CDNs (läuft offline im LAN).

Neu (2026-11): Katalog `/neu` (`app/catalog.py`), Einsatz-Assistent `/neu/bin`, Baum `/baum`, D30-Direktdruck (`app/d30.py`, Env `LAGER_D30*`), Trockner-Scan, Filament/Harz-Dropdowns (`app/choices.py`). Hinzufügen: Katalog, Behälter (`/neu/behaelter`), Kabel & Material (`/neu/material`). Typen am Teil (`item.ctype`/`cfields`, `app/sortiment.py`, `/sortiment`), Offline-App (`app/static/sw.js`).
Cloud/CI: Hardware (D30-Bluetooth) ist nur gemockt testbar; Rest läuft überall. Einstieg: `docs/DEVELOPMENT.md`.

Mehr: `README.md`, `docs/DEVELOPMENT.md`, `docs/CONFIG.md`, `docs/DEPLOYMENT.md`, `docs/FEATURES.md`, `docs/API.md`, `docs/WINDOWS.md`, `docs/ANDROID.md`, `docs/HOME_ASSISTANT.md`, `docs/INSTALL.md`, `docs/RELEASE.md`, `docs/STATUS.md` (Stand + Meilensteine), `docs/ARCHITECTURE.md` (Datenmodell), `docs/DECISIONS.md`, `docs/ETIKETTEN.md` (Code-Schema, D30)
