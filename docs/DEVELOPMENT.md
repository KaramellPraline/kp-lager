# Entwicklung

Diese Anleitung ist so geschrieben, dass eine neue Sitzung (auch Claude Code in der Cloud) ohne
Vorwissen weiterarbeiten kann.

## Einstieg in 5 Minuten

1. `README.md`, `CLAUDE.md` und `docs/STATUS.md` lesen (Stand, offene Aufgaben, Regeln).
2. Umgebung: `uv sync --all-groups` (Python ≥ 3.12 wird von uv geholt). Ohne CAD: `uv sync --group dev --group mcp`.
3. Starten: `uv run uvicorn app.main:app --reload --port 8000` → http://localhost:8000
4. Prüfen, bevor etwas fertig gemeldet wird:
   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run mypy app
   uv run python -m pytest -q --ignore=tests/test_cad.py
   ```
   (`python -m pytest` statt `pytest`: unter Windows blockiert die Anwendungssteuerung teils `pytest.exe`.)

## Arbeitsweise

- Pro Aufgabe ein Branch (`feat/…`, `fix/…`), kleine thematische Commits, danach PR bzw. Merge nach `main`.
- Aufgaben stehen in `docs/STATUS.md`. Nach jeder Arbeit dort Stand/offene Punkte aktualisieren;
  Entscheidungen mit Datum und Begründung in `docs/DECISIONS.md`; Aufbau in `docs/ARCHITECTURE.md`.
- Bei Bugs zuerst ein reproduzierender Test, dann der Fix.
- Schemaänderungen **nur** als neue nummerierte SQL-Datei in `app/migrations/` (nächste Nummer: siehe Ordner;
  der Runner nutzt `PRAGMA user_version`). Bestehende Migrationen nie ändern.
- Kein JS-Build, keine CDNs: JS/CSS liegen in `app/static/` und laufen offline.
- Mobile first, aber Katalog/Einsatz-Assistent/Baum sind für den Desktop optimiert.
- Texte der Oberfläche auf Deutsch, Umlaute korrekt.

## Projektaufbau (Wo liegt was?)

| Thema | Dateien |
|---|---|
| App-Start, Routen | `app/main.py`, `app/web.py` (Hauptrouten, Schnelleingabe), `app/web_ops.py` (Betrieb: Status, Trockner, Slicer, Massenaktionen, D30-Status), `app/web_katalog.py` (Katalog, Einsatz-Assistent, Baum), `app/api.py` (REST) |
| Datenzugriff | `app/db.py` (Verbindung, Migrationen), `app/repo.py` (Behälter/Teile), `app/codes.py` (Code-Schema), `app/kinds.py` (Behälterarten) |
| Anlegen | `app/catalog.py` (Teile-Typen, Namensvorlagen), `app/choices.py` (Auswahllisten Filament/Harz), `app/quick.py` (Schnelleingabe-Parser), `app/creation.py` (API/MCP), `app/importer.py` |
| Etiketten | `app/labels.py` (Listen, XLSX), `app/labelimg.py` (Bild 320×96), `app/d30.py` (Bluetooth-Druck) |
| Sortierkasten | `app/kasten.py`, `cad/norb_bins.py`, `cad/bin_params.json` |
| Material | `app/materials.py`, `app/dryer.py`, `app/slicer.py`, `app/vision.py`, `app/value.py` |
| Betrieb | `app/scheduler.py` (Backup täglich), `app/backup.py`, `app/status.py`, `app/config.py` |
| Oberfläche | `app/templates/`, `app/static/app.js`, `app/static/style.css` (Design „Crimson Night Core“) |
| Schnittstellen | `tools/lager_client.py`, `tools/lager_cli.py`, `tools/lager_mcp.py` |

Jinja-Hinweis: `base.html` benutzt die Variable `cur` (aktueller Pfad) – eigene Template-Variablen
dürfen nicht `cur` heißen.

## Tests

- `uv run python -m pytest -q --ignore=tests/test_cad.py` (~260 Tests, ~30 s). `tests/conftest.py` liefert den Fixture `client`
  mit temporärem Datenverzeichnis; Auto-Backup ist in Tests aus.
- CAD-Tests: `uv sync --group cad` und `uv run --group cad python -m pytest tests/test_cad.py`.
- Hardware wird gemockt: D30 (`app.d30.send/status` per monkeypatch).
- Neue Funktion → Test in `tests/test_<thema>.py`.

## Arbeiten in der Cloud (Claude Code, GitHub Codespaces o. ä.)

Einrichtung Schritt für Schritt: [CLOUD.md](CLOUD.md) (Hook `.claude/hooks/session-start.sh`, `.devcontainer/`).

Funktioniert vollständig für alles außer Hardware:

- Läuft in der Cloud: App, API, Tests, Lint, Typecheck, Katalog, Baum, Etiketten als Bild (`/labels/img/<CODE>.png`), XLSX-Export.
- Läuft nur am Server-PC: D30-Druck (Bluetooth), Windows-Skripte (`tools/serve.ps1`).
- Eine Test-Instanz für die Oberfläche: `LAGER_DATA_DIR=/tmp/lager LAGER_AUTO_BACKUP=0 LAGER_D30=0 uv run uvicorn app.main:app --port 8000`.
- CI (`.github/workflows/ci.yml`) führt Lint, Typecheck und Tests bei jedem Push und PR aus.
- Geheimnisse gehören nicht ins Repository: `.env`, API-Schlüssel (`LAGER_API_KEY`), Zertifikate, `data/`.

## Typische Aufgaben

- **Neuen Teile-Typ im Katalog:** in `app/catalog.py` eine `Type(...)` ergänzen (Felder als `F(key, label, "opt1|opt2")`,
  Namensvorlage in `parts`). `tests/test_katalog.py::test_every_type_is_usable` prüft sie automatisch.
- **Neue Behälterart:** in der App unter Behälter → „Neue Art …“ (dynamisch) oder fest in `app/kinds.py` (`BUILTIN`).
- **Neues Feld/Tabelle:** Migration `app/migrations/NNN_name.sql`, dann `repo.py`, Routen, Template, Test.
- **Neue Einstellung:** `app/prefs.py` (Register) – `/settings` wird daraus erzeugt.
- **Neue Umgebungsvariable:** `app/config.py` + `docs/CONFIG.md`.

## Bekannte Stolpersteine

- Windows PowerShell 5.1 braucht für `tools/serve.ps1` eine UTF-8-BOM.
- Kleine HTMX-Swaps ersetzen Zeilen (`outerHTML`); Listen mit `data-collapse` bauen den „Mehr“-Knopf nach dem Laden auf.
- Ausgeblendete Formularfelder werden per JS `disabled`, damit sie nicht mitgeschickt werden (sonst überschreiben gleichnamige Felder).
- Tags werden kleingeschrieben gespeichert.
