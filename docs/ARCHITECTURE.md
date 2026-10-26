# Architektur

## Überblick
Ein FastAPI-Prozess rendert HTML (Jinja2 + HTMX) und spricht direkt mit einer SQLite-Datei. Caddy davor terminiert HTTPS (nötig für Kamera/Mikrofon im Browser). Whisper läuft später als optionaler Zusatzdienst.

```
Handy (QR scannen) → https://lager.home.lan/c/0042 → Caddy → uvicorn/FastAPI → SQLite (+ data/photos/)
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
- `item`: `id`, `code` (ART-0001, UNIQUE, optional), `label_printed`, `container_id`, `name`, `qty` (NULL = ungezählt, nie < 0), `qty_hint` („ca. 20“, „viele“), `unit`, `tags`, `notes`, `photo`, Zeitstempel.
- `event`: Protokoll (`add|take|put|move|edit|delete|import`, `delta`, `note`); `item_name` als Kopie, bleibt nach Löschen erhalten.
- Ab M3: `item_fts` (FTS5 trigram) über Name, Tags, Notizen.
- Codes werden vorab gedruckt; Code ohne Zeile in `container` = noch frei.

## Dateien
- `app/main.py`: Einstiegspunkt (`create_app(load_settings())`)
- `app/config.py`: Settings aus Env (`LAGER_DATA_DIR`, `LAGER_BASE_URL`)
- `app/web.py`: alle Routen; Verbindung pro Request; Fehler (`LagerError`) → Redirect mit `?msg=`
- `app/db.py`: Verbindung (FK an, WAL, `fold()` für Umlaut-LIKE) + Migrations-Runner (PRAGMA user_version)
- `app/repo.py`: Datenzugriff Behälter-Baum (Pfad, Umzug, Raster, Löschen), Items (Bestand), Protokoll, Suche
- `app/migrations/`: `001_init` Schema, `002_fts` Volltextindex + Trigger, `003_meta` Zähler/Einstellungen, `004_codes` Item-Codes + Druckstatus
- `app/codes.py`: Code-Schema PRÄFIX-NNN, Normalisieren, Zähler je Präfix, Einstellungen (`meta`)
- `app/labels.py`: QR-Inhalt (Großbuchstaben), XLSX für D30 (40×12), Etikettenlisten, `finalize()` (Export: Namen speichern, gedruckt markieren, Codes reservieren)
- `app/importer.py`: Haiku-JSON parsen/validieren, Vorschau auf DB-Kopie, Export
- `app/photos.py`: Foto speichern (EXIF-Drehung, 1600 px + Thumbnail), löschen
- `app/templates/`: `node.html` (Behälter), `item.html`, `search.html`, `import.html`, `labels.html` (Druck), Partials `_*.html`
- `deploy/`: install.sh, systemd-Units, Caddyfile, backup.sh, README
- `tests/`: pytest (`conftest.py` liefert `client` mit Temp-Datenverzeichnis)

## Wichtige Routen
- `/c/{code}` bzw. `/C/{code}` QR-Einstieg (Behälter oder Teil) · `/n/{id}` Behälter · `/items/{id}` Teil · `/suche?q=` · `/labels` · `/settings` · `/import` · `/export.json`
- Etiketten: `POST /labels/preview` (source=blank|pending|container|item → editierbare Tabelle), `POST /labels/export` (fmt=xlsx|a8)
- Umlagern: `POST /carry/{item|node}/{id}` setzt Cookie, `POST /drop/{id}` legt ab.

## Schnittstellen
- Keine externen Dienste im Betrieb. Erst-Inventur: manuell im Claude-Chat (Haiku) → JSON → `/import`.
