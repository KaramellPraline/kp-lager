# KP Lager (Repo: sortiersystem)

Zweck: Selbst gehostetes Lagersystem; QR-Code auf Behälter → Handy-Browser zeigt Inhalt, Einlagern/Entnehmen/Suchen im LAN.
Stack: Python ≥3.12, FastAPI, Jinja2 + HTMX (vendored, kein JS-Build), SQLite (stdlib `sqlite3`, kein ORM, FTS5), segno (QR), Pillow, uv. Betrieb: Debian-LXC, systemd, Caddy.

## Befehle
- Run (dev): `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` (Daten in `./data`)
- Test: `uv run pytest -q`
- Lint/Typecheck: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
- Deploy: siehe `deploy/README.md`

## Secrets
- Aktuell keine. KI-API ist bewusst nicht eingebunden (siehe DECISIONS).

## Regeln
- Arbeit in Meilensteinen aus `docs/STATUS.md`; pro Meilenstein ein Branch `feat/mX-…`, Abnahmekriterien = Tests.
- Kern muss ohne KI-Komponenten laufen (Whisper/Embeddings optional, per Config abschaltbar).
- Mobile first: jede Seite per Daumen bedienbar, max. 2 Taps für Entnehmen/Einlagern.
- Schema-Änderungen nur als nummerierte SQL-Dateien in `app/migrations/`.
- Keine externen CDNs (läuft offline im LAN).

Mehr: `docs/STATUS.md` (Stand + Meilensteine), `docs/ARCHITECTURE.md` (Datenmodell), `docs/DECISIONS.md`, `docs/HAIKU_PROMPT.md` (Erst-Inventur per Chat), `docs/ETIKETTEN.md` (Code-Schema, D30)
