# KP Lager (sortiersystem)

Selbst gehostetes Lager-Inventar für Werkstatt, Heimwerken, 3D-Druck, Laser und Elektronik.
QR-Etiketten auf Behältern und Teilen → Handy-Browser zeigt den Inhalt; Einlagern, Entnehmen,
Suchen und Umlagern im Heimnetz (LAN). Alles läuft lokal, ohne Cloud und ohne externe CDNs.

- **Stack:** Python ≥ 3.12 · FastAPI · Jinja2 + HTMX (vendored, kein JS-Build) · SQLite (stdlib, FTS5) ·
  segno (QR) · Pillow · uv · pytest · ruff · mypy (strict)
- **Sprache der Oberfläche:** Deutsch (Englisch für Behälterarten wählbar)
- **Betrieb:** Windows-PC (`tools/serve.ps1`) oder Docker Compose (App + Caddy, HTTPS) – läuft auf amd64 und arm64 (Raspberry Pi)

## Funktionen (Überblick)

| Bereich | Was es kann |
|---|---|
| Behälter & Teile | Baum aus Räumen, Regalen, Boxen, Sortierkästen, Einsätzen und Fächern; Teile mit Menge, Einheit, Tags, Fotos, Mindestbestand, Preis |
| Anlegen | Schnelleingabe auf der Startseite · **Katalog** (`/neu`, ~55 Teile-Typen mit Auswahlfeldern) · **Einsatz-Assistent** (`/neu/bin`) · Spracheingabe · Foto-Erkennung (lokale KI) |
| Übersicht | Aufklappbarer Baum (`/baum`, Startseite), Suche mit Tippfehlern/Synonymen, Freie Plätze, Verlauf, Rückgängig |
| Etiketten | Code-Schema `PRÄFIX-NNN`, QR, XLSX/A4/A8, **D30-Direktdruck per Bluetooth** (40×12 mm), Warteschlange, Inhaltsetiketten |
| Sortierkästen | Modell Kistenberg NORB16 (5×7), Einsätze X×Y mit Fächern, Draufsicht, parametrischer Bin-Generator (`cad/`) |
| 3D-Druck & Material | Filament/Harz mit Datenblatt, Restmenge per Wägung, Trockner-Programme + Scan-Ablauf, Slicer-Import (Creality Print/Orca/Cura) |
| Betrieb | Tägliches Backup, Statusseite, Einkaufsliste mit Mindestbestand, Lagerwert, Massenbearbeitung |
| Schnittstellen | REST `/api/v1`, CLI (`tools/lager_cli.py`), MCP-Server (`tools/lager_mcp.py`) – Kategorien und Felder immer live aus dem Schema |

Eine ausführliche Beschreibung steht in [docs/FEATURES.md](docs/FEATURES.md).

## Schnellstart (Entwicklung)

Voraussetzung: [uv](https://docs.astral.sh/uv/) (installiert Python automatisch).

```bash
git clone <repo-url> sortiersystem && cd sortiersystem
uv sync --all-groups            # Abhängigkeiten (ohne --group cad geht es auch, siehe unten)
uv run uvicorn app.main:app --reload --port 8000
# → http://localhost:8000 (Daten in ./data, wird automatisch angelegt)
```

Tests und Qualität (muss grün sein, bevor etwas gemerged wird):

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run python -m pytest -q --ignore=tests/test_cad.py     # CAD-Tests brauchen: uv sync --group cad
```

Kamera-Scan und Mikrofon funktionieren im Browser nur über HTTPS. Für LAN-Betrieb siehe
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Dokumentation

| Datei | Inhalt |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Kurzanleitung für Claude Code / Cloud-Sitzungen (Befehle, Regeln) |
| [docs/STATUS.md](docs/STATUS.md) | Aktueller Stand, Meilensteine, offene Aufgaben – **hier weiterarbeiten** |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Entwicklungs-Workflow, Projektaufbau, Tests, Arbeiten in der Cloud |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Datenmodell, Module, Routen |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Entscheidungen mit Datum und Begründung (nicht neu diskutieren) |
| [docs/CONFIG.md](docs/CONFIG.md) | Umgebungsvariablen und Einstellungen |
| [docs/CLOUD.md](docs/CLOUD.md) | Einrichtung für Claude Code im Web und Codespaces |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Windows-PC, Docker, Raspberry Pi, HTTPS, Backup |
| [docs/FEATURES.md](docs/FEATURES.md) | Funktionen und Bedienung im Detail |
| [docs/ETIKETTEN.md](docs/ETIKETTEN.md) | Code-Schema, XLSX/D30-Vorlage |
| [docs/DIREKTDRUCK.md](docs/DIREKTDRUCK.md) | D30-Direktdruck (Bluetooth, Protokoll, Fehlersuche) |
| [docs/NORB16.md](docs/NORB16.md), [docs/BIN_SPEC.md](docs/BIN_SPEC.md) | Sortierkasten und Bin-Spezifikation (+ `cad/bin_params.json`) |
| [deploy/README.md](deploy/README.md) | Docker-Deployment, Handy-Einrichtung |

## Projektstruktur

```
app/            FastAPI-App (Routen: web.py, web_ops.py, web_katalog.py, api.py), Fachlogik je Modul
app/templates/  Jinja2-Seiten und Partials     app/static/  CSS, JS, vendored htmx/jsQR, Schriften
app/migrations/ nummerierte SQL-Migrationen (einzige Quelle für Schemaänderungen)
tests/          pytest (conftest.py: Test-Client mit temporärem Datenverzeichnis)
tools/          CLI, MCP-Server, D30-Druck, Zertifikat, serve.ps1 (Windows-Start)
cad/            parametrischer Bin-Generator (build123d, Gruppe cad) + Parameter-JSON
deploy/         Docker Compose + Caddy;  Dockerfile im Wurzelverzeichnis
docs/           Dokumentation
data/           Laufzeitdaten (SQLite, Fotos, Backups) – nicht im Repository
```

## Hardware-abhängige Teile

Diese Funktionen brauchen den Server-PC mit Bluetooth bzw. lokale KI und sind in der Cloud/CI nur
über Mocks getestet:

- **D30-Direktdruck** (Bluetooth-Seriell/COM oder BLE; Paket `bleak`/`pyserial`) – `app/d30.py`
- **CAD** (`cad/norb_bins.py`, build123d) – nur mit `uv sync --group cad`

## Lizenz und Daten

MIT-Lizenz, siehe [LICENSE](LICENSE). Das Repository ist privat und enthält keine Nutzdaten: `data/`, Fotos,
Datenbanken und Zertifikate sind per `.gitignore` ausgeschlossen.
