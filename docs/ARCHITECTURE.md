# Architektur

## Überblick
Ein FastAPI-Prozess rendert HTML (Jinja2 + HTMX) und spricht direkt mit einer SQLite-Datei. Caddy davor terminiert HTTPS (nötig für Kamera/Mikrofon im Browser). Whisper läuft später als optionaler Zusatzdienst.

```
Handy (QR scannen) → https://lager.home/c/0042 → Caddy → uvicorn/FastAPI → SQLite (+ data/photos/)
                                                              └→ (optional) whisper-Dienst
```

## Datenmodell (SQLite)
- `container`: `code` (PK, z. B. `0042`, steht im QR), `name`, `kind` (raum|regal|eurobox|kiste|sortierkasten|sonstiges), `parent_code` (Hierarchie; Umzug = parent ändern), `grid` (z. B. `6x8` für Sortierkästen), `notes`, `photo`, `created_at`, `updated_at`.
- `item`: `id`, `container_code`, `slot` (Fach, z. B. `B3`, optional), `name`, `qty` (INT, NULL = ungezählt), `qty_hint` (z. B. „ca.“, „viele“), `unit`, `tags` (Freitext), `notes`, `photo`, `updated_at`.
- `event`: `id`, `ts`, `item_id`, `container_code`, `action` (add|take|move|edit|import), `delta`, `note` – Protokoll statt nur Bestand („wo war X zuletzt?“).
- `item_fts`: FTS5 (`tokenize='trigram'`) über Name, Tags, Notizen + Behältername.
- Codes werden vorab gedruckt; ein Code ohne Zeile in `container` = noch frei.

## Geplante Dateien
- `app/main.py`: FastAPI-App, Routen
- `app/db.py`: Verbindung, Migrations-Runner
- `app/repo.py`: Datenzugriff (Behälter, Items, Events, Suche)
- `app/migrations/NNN_*.sql`: Schema
- `app/templates/`, `app/static/`: Jinja2-Templates, htmx, CSS
- `app/labels.py`: QR-Etikettenbögen
- `app/importer.py`: JSON-Import/Export
- `deploy/`: systemd-Unit, Caddyfile, Backup-Skript
- `tests/`: pytest

## Schnittstellen
- Keine externen Dienste im Betrieb. Erst-Inventur: manuell im Claude-Chat (Haiku) → JSON → `/import`.
