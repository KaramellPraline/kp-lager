# Architektur

## Überblick
Ein FastAPI-Prozess rendert HTML (Jinja2 + HTMX) und spricht direkt mit einer SQLite-Datei. Caddy davor terminiert HTTPS (nötig für Kamera/Mikrofon im Browser). Whisper läuft später als optionaler Zusatzdienst.

```
Handy (QR scannen) → https://lager.home.lan/c/0042 → Caddy → uvicorn/FastAPI → SQLite (+ data/photos/)
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

- `container`: `id` (intern), `code` (QR-ID, UNIQUE, nur etikettierte Knoten), `parent_id`, `kind` (englische Schlüssel aus `app/kinds.py`, z. B. room|shelf|toolbox|eurobox|sortingbox|bin|compartment, plus eigene aus `container_kind`), `name`, `position` (Platz im Eltern, z. B. `B3`), `grid` (`SpaltenxZeilen` → Fächer A1… als Kind-Knoten), `notes`, `photo`, Zeitstempel. Löschen nur wenn leer (RESTRICT).
- `item`: `id`, `code` (ART-0001, UNIQUE, optional), `label_printed`, `container_id`, `name`, `qty` (NULL = ungezählt, nie < 0), `qty_hint` („ca. 20“, „viele“), `unit`, `tags`, `notes`, `photo`, Zeitstempel.
- `event`: Protokoll (`add|take|put|move|edit|delete|import`, `delta`, `note`); `item_name` als Kopie, bleibt nach Löschen erhalten.
- Ab M3: `item_fts` (FTS5 trigram) über Name, Tags, Notizen.
- Codes werden vorab gedruckt; Code ohne Zeile in `container` = noch frei.

## Dateien
- `app/main.py`: Einstiegspunkt (`create_app(load_settings())`)
- `app/config.py`: Settings aus Env (`LAGER_DATA_DIR`, `LAGER_BASE_URL`)
- `app/web/`: Oberfläche (Karte siehe „Routen-Karte“ unten); Verbindung pro Request (`app/deps.py`); Fehler (`LagerError`) → Redirect mit `?msg=`
- `app/db.py`: Verbindung (FK an, WAL, `fold()` für Umlaut-LIKE) + Migrations-Runner (PRAGMA user_version)
- `app/repo.py`: Datenzugriff Behälter-Baum (Pfad, Umzug, Raster, Löschen), Items (Bestand), Protokoll, Suche
- `app/migrations/`: `001_init` Schema, `002_fts` Volltextindex + Trigger, `003_meta` Zähler/Einstellungen, `004_codes` Item-Codes + Druckstatus, `005_alltag` Rückgängig/Verleihen/Einkauf/Favoriten, `006_einsaetze` Art „einsatz“, size/model, `label_queue`
- `app/codes.py`: Code-Schema PRÄFIX-NNN, Normalisieren, Zähler je Präfix, Einstellungen (`meta`)
- `app/a4.py`: A4-Etiketten (Typen, Rendering 300 dpi, `pack`, PDF, IPP, Queue `a4_job`) · `app/web/routes/drucken_a4.py`: Routen dazu, Bin-Etikett-Editor, `bins.json` · `app/presets.py`: Klassen je Typ (`preset`)
- `app/labels.py`: QR-Inhalt (Großbuchstaben), Layout je Typ, D30-Warteschlange, Etikettenlisten, `finalize()` (Export: Namen speichern, gedruckt markieren, Codes reservieren)
- `app/importer.py`: Haiku-JSON parsen/validieren, Vorschau auf DB-Kopie, Export
- `app/kasten.py`: Kastenmodelle (NORB16 5×7, Griff C1–E1), Einsätze platzieren/prüfen, Draufsicht-Daten, Schnelleingabe-Ziele
- `app/prefs.py`: Einstellungsregister (Typ, Standard, Gruppe) → `/settings` generiert, Werte in `meta`
- `app/search.py`: Suche (Wortliste DE/EN, Stämme, Synonyme, Tippfehler je Wort, Tag-Filter), genutzt von /suche und /api/v1/search
- `app/materials.py`: Filament/Harz-Eigenschaften (Felder, Datenblatt-Ansicht, €/kg), JSON in `item.specs`; `item.order_url`/`price` für alle Teile
- `app/kinds.py`: Behälter-Arten (fest + Tabelle `container_kind`), `sync` bei jedem `connect` aktualisiert KINDS/Präfixe
- `app/api/`, `app/apikeys.py`: REST `/api/v1`, Schlüssel nur als SHA-256 in `api_key`
- `tools/lager_client.py` (httpx), `tools/lager_cli.py` (argparse), `tools/lager_mcp.py` (FastMCP stdio, Gruppe `mcp`, `mcp<2`)
- `tools/devcert.py`: lokale CA + Zertifikate für lokales HTTPS
- `cad/norb_bins.py`: parametrischer Bin-Generator (build123d, Gruppe `cad`)
- `app/quick.py`: Schnelleingabe-Parser („3 Rollen Lötzinn“), Standard-Synonyme
- `app/backup.py`: `python -m app.backup` – SQLite-Kopie + Foto-Archiv, Aufräumen
- `app/static/app.js`: Kopieren, Mikrofon → `/api/transcribe`; `jsQR.js` Scan-Fallback ohne BarcodeDetector
- `Dockerfile`, `deploy/compose.yaml`, `deploy/Caddyfile`: App + Caddy (tls internal, `/ca.crt`)
- `app/photos.py`: Foto speichern (EXIF-Drehung, 1600 px + Thumbnail), löschen
- `app/templates/`: `node.html` (Behälter), `item.html`, `search.html`, `import.html`, `labels.html` (Druck), Partials `_*.html`
- `deploy/`: install.sh, systemd-Units, Caddyfile, backup.sh, README
- `tests/`: pytest (`conftest.py` liefert `client` mit Temp-Datenverzeichnis)

## Routen-Karte (Bereich → Datei)
Jedes Routenmodul hat dieselbe Form `register(app, ctx)`; `ctx` (`app/web/shared.py: Ctx`) liefert Einstellungen, `render`, `direct_print`, `print_or_queue`, `photo_dir`, `sheet_dir`; die Verbindung kommt als `conn: Conn` (`app/deps.py`).

| Bereich (Oberfläche) | Pfade | Datei |
|---|---|---|
| App-Fabrik, Mounts, Fehler, Middleware | – | `app/web/app.py` (`create_app`, Export über `app/web/__init__.py`) |
| Gemeinsames | Templates, `redirect`, Cookies, Formular-Hilfen, `Ctx` | `app/web/shared.py` |
| Bestand | `/`, `/n/<id>` (Bearbeiten, Code, Foto, Löschen, Einsätze), `/suche`, `/baum`, `/zu-sortieren`, `/platz`, Favorit, `/carry`·`/drop`, `/auswahl`·`/bulk` | `app/web/routes/bestand.py` |
| Teile | `/items/<id>` (Bearbeiten, Code, Menge, Datenblatt, Foto, Typ, Löschen), `/n/<id>/items`, `/items/new`, `/typen` (Tags), Karten `/cards` | `app/web/routes/teile.py` |
| Sortiment | `/sortiment…`, `/material` | `app/web/routes/sortiment.py` |
| Hinzufügen | `/neu/go`, `/neu/behaelter`, `/neu/material`, `/neu/platz`, `/quickadd`, `/containers`, `/n/<id>/quickadd` | `app/web/routes/hinzufuegen.py` |
| Hinzufügen › Katalog | `/neu`, `/neu/vorschau`, `/neu/etikett.png`, `/neu/bin` | `app/web/routes/katalog.py` |
| Scan | `/c/<code>`, `/scan`, `/api/take`, `/api/move`, `/api/move-batch`, `/api/code/<code>`, `/api/projects/<id>/gather` | `app/web/routes/scan.py` |
| Drucken | `/labels…`, `/etiketten/typ…`, `/d30/…`, `/druck/wiederholen` | `app/web/routes/drucken.py` |
| Drucken › A4 | `/a4…`, `/n/<id>/etikett`, `/labels/bins.json` | `app/web/routes/drucken_a4.py` |
| Einkauf | `/einkauf…`, `/lieferanten…`, `/purchases…`, bestellt/eingetroffen/Mindestbestand | `app/web/routes/einkauf.py` |
| Werkstatt | `/projekte…`, `/entnahmen`, `/verliehen`, `/inventur…`, `/trockner…`, `/slicer…`, `/ablauf`, Waage | `app/web/routes/werkstatt.py` |
| System | `/settings…` (Admin, Schlüssel, A4-Drucker, Node-Typen), `/status…`, `/import`, `/export.*`, `/codes`, `/arten`, `/lang`, `/mehr`, `/verlauf`, Rückgängig, `/health`, `/ca.crt`, `/sw.js`, `/manifest.webmanifest`, `/offline` | `app/web/routes/system.py` |
| REST `/api/v1` | Gemeinsames (JSON-Form, Schlüssel, Nachschlagen) · Bestand · Werkstatt · Einkauf · System | `app/api/common.py`, `bestand.py`, `werkstatt.py`, `einkauf.py`, `system.py`; `build_router` in `app/api/__init__.py` |

Reihenfolge der Registrierung: `app/web/routes/__init__.py: ROUTES` (bei gleichem Pfad gewinnt die erste Route, z. B. `/sortiment/eigene` vor `/sortiment/{key}`).

## Wichtige Routen
- `/c/{code}` bzw. `/C/{code}` QR-Einstieg (Behälter oder Teil) · `/n/{id}` Behälter · `/items/{id}` Teil · `/suche?q=` · `/labels` · `/settings` · `/import` · `/export.json`
- Etiketten: `POST /labels/preview` (source=blank|pending|container|item → editierbare Tabelle), `POST /labels/export` (fmt=d30|queue|a4q) · `/a4` (Warteschlange, `/a4/drucken` nur mit confirm) · `/n/<Einsatz>/etikett` · `/labels/bins.json`
- Umlagern: `POST /carry/{item|node}/{id}` setzt Cookie, `POST /drop/{id}` legt ab.
- Alltag: `POST /undo/{event}`, `/verlauf`, `/verliehen`, `/einkauf`, `/platz`, `/scan`, `/manifest.webmanifest`
- JSON: `GET /api/code/{code}`, `POST /api/move` (Scan-Einräumen)

## Schnittstellen
- Keine externen Dienste im Betrieb. Erst-Inventur: manuell im Claude-Chat (Haiku) → JSON → `/import`.

- `app/scheduler.py` tägliches Backup · `app/status.py` Statusseite · `app/value.py` Lagerwert · `app/dryer.py` Trockner · `app/slicer.py` G-Code/3MF-Verbrauch · `app/vision.py` Foto-Erkennung · `app/bulk.py` Massenaktionen · `app/creation.py` Teile mit Kategorie anlegen (API/MCP) · Routen dazu in `app/web/routes/` (`system.py`, `werkstatt.py`, `bestand.py`)

- `app/catalog.py` Teile-Katalog: `AREAS` (Bereich › Gruppe), `TYPES` (bis 1.3, Reihenfolge fest) + `TYPES_2_0`, Felder, Namensvorlagen, Zusatzfeld-Profile `EXTRAS` (`Type.extras`), Erkennung `guess`; Elektronik → Profil `cmp` · `app/choices.py` Auswahllisten Filament/Harz · `app/web/routes/katalog.py` Routen `/neu`, `/neu/vorschau`, `/neu/bin` (Baum `/baum`, `/n/<id>/zweig` in `bestand.py`)
- `app/labelimg.py` Etikettenbild 320×96 (QR, Name auto-Größe, ID) · `app/d30.py` Druck: Bluetooth-Seriell (COM) → BLE-Rückfall, Status-Scan, `print_codes`/`print_labels` · `tools/d30_print.py` Kommandozeile
- Migrationen 017 (Betrieb: Haltbarkeit, Maße, Trockner, Slicer) und 018 (`container.airtight`)
- Neue Behälterarten `machine` (MAS) und `dryer` (TRO); Scan-Ablauf Trockner → Filament in `app/web/routes/scan.py: by_code` (Cookie `dryer_wait`, 10 min)
- Cookies der Bedienung: `qa_targets` (Ziele), `qa_cats`/`qa_kinds` (zuletzt benutzte Kategorien/Arten), `kat_typ` (letzter Katalog-Typ)
