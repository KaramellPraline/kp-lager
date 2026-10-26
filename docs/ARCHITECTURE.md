# Architektur

## Überblick
Ein FastAPI-Prozess rendert HTML (Jinja2 + HTMX) und spricht direkt mit einer SQLite-Datei. Caddy davor terminiert HTTPS (nötig für Kamera/Mikrofon im Browser). Whisper läuft später als optionaler Zusatzdienst.

```
Handy (QR scannen) → https://lager.home/c/0042 → Caddy → uvicorn/FastAPI → SQLite (+ data/photos/)
                                                              └→ (optional) whisper-Dienst
```

## Datenmodell (SQLite)
Schema: `app/migrations/001_init.sql`. Prinzip: **ein Baum aus Behältern, Items hängen an genau einem Knoten.**

```
Keller (raum)
└─ Regal 1 (regal)
   ├─ Ebene 2 (ebene)
   │  └─ Elektronik (eurobox, code 0042) ── Items: Lötzinn ×3, Multimeter ×1
   └─ Schrauben (sortierkasten, code 0043, grid 6x8)
      └─ Fach B3 (fach, automatisch) ── Items: Holzschrauben 4x40 (viele)
└─ Kistenberg (stapel) ── Kisten wandern per move_container
```

- `container`: `id` (intern), `code` (QR-ID, UNIQUE, nur etikettierte Knoten), `parent_id`, `kind` (raum|regal|ebene|stapel|eurobox|kiste|sortierkasten|fach|sonstiges), `name`, `position` (Platz im Eltern, z. B. `B3`), `grid` (`SpaltenxZeilen` → Fächer A1… als Kind-Knoten), `notes`, `photo`, Zeitstempel. Löschen nur wenn leer (RESTRICT).
- `item`: `id`, `container_id`, `name`, `qty` (NULL = ungezählt, nie < 0), `qty_hint` („ca. 20“, „viele“), `unit`, `tags`, `notes`, `photo`, Zeitstempel.
- `event`: Protokoll (`add|take|put|move|edit|delete|import`, `delta`, `note`); `item_name` als Kopie, bleibt nach Löschen erhalten.
- Ab M3: `item_fts` (FTS5 trigram) über Name, Tags, Notizen.
- Codes werden vorab gedruckt; Code ohne Zeile in `container` = noch frei.

## Geplante Dateien
- `app/main.py`: FastAPI-App, Routen
- `app/db.py`: Verbindung (FK an, WAL) + Migrations-Runner (PRAGMA user_version)
- `app/repo.py`: Datenzugriff Behälter-Baum (Pfad, Umzug, Raster), Items (Bestand), Protokoll
- `app/migrations/NNN_*.sql`: Schema
- `app/templates/`, `app/static/`: Jinja2-Templates, htmx, CSS
- `app/labels.py`: QR-Etikettenbögen
- `app/importer.py`: JSON-Import/Export
- `deploy/`: systemd-Unit, Caddyfile, Backup-Skript
- `tests/`: pytest

## Schnittstellen
- Keine externen Dienste im Betrieb. Erst-Inventur: manuell im Claude-Chat (Haiku) → JSON → `/import`.
