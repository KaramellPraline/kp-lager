# Weiterarbeiten in der Cloud

Das Repository ist für Claude Code im Web (claude.ai/code) und GitHub Codespaces vorbereitet.

## Claude Code im Web

1. claude.ai/code öffnen → GitHub verbinden (Claude-GitHub-App für das **private** Repo `KaramellPraline/sortiersystem` freigeben).
2. Neue Sitzung → Repository `sortiersystem`, Branch `main` wählen.
3. Umgebung (Einstellungen der Cloud-Umgebung):
   - Netzwerkzugriff: mindestens PyPI (`pypi.org`, `files.pythonhosted.org`) und GitHub erlauben.
   - Setup-Skript (falls der SessionStart-Hook nicht reicht): `pip install uv && uv sync --group dev --group mcp`
4. Der Hook `.claude/hooks/session-start.sh` richtet bei jeder Cloud-Sitzung automatisch die Abhängigkeiten ein und setzt
   `LAGER_DATA_DIR=/tmp/lager-data`, `LAGER_AUTO_BACKUP=0`, `LAGER_D30=0`.
5. Erste Anweisung für die Sitzung, z. B.:
   > Lies README.md, CLAUDE.md, docs/DEVELOPMENT.md und docs/STATUS.md. Setze den nächsten offenen Punkt um (eigener Branch),
   > bis Lint, Typecheck und Tests grün sind, und öffne einen PR.

## GitHub Codespaces

`.devcontainer/devcontainer.json` (Python 3.12, uv). Nach dem Start: `uv run uvicorn app.main:app --reload --port 8000`,
Port 8000 wird weitergeleitet.

## Was in der Cloud geht – und was nicht

- Geht: App starten, Tests/Lint/Typecheck, Katalog, Baum, API/CLI/MCP, Etikettenbild, XLSX, Migrationen.
- Nur am Windows-PC: D30-Druck (Bluetooth, Client mit Bridge).
- Änderungen kommen per PR zurück nach `main`; auf dem Server dann `docker compose up -d --build` (oder neue Version ziehen).
- Geheimnisse (`LAGER_API_KEY`, Tokens) nie ins Repo; in der Cloud-Umgebung als Secret/Umgebungsvariable setzen.
