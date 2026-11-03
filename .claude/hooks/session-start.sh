#!/usr/bin/env bash
# Claude Code in der Cloud: Abhängigkeiten einrichten (läuft nur dort, lokal nichts tun).
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}"
command -v uv >/dev/null 2>&1 || pip install --quiet uv
uv sync --quiet --group dev --group mcp
# Test-Instanz ohne Hardware und ohne Hintergrunddienste
{
  echo 'export LAGER_DATA_DIR=/tmp/lager-data'
  echo 'export LAGER_AUTO_BACKUP=0'
  echo 'export LAGER_D30=0'
} >> "${CLAUDE_ENV_FILE:-/dev/null}"
