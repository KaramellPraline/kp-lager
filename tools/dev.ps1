# KP Lager zum Debuggen auf diesem PC starten (ohne Docker, ohne Installer).
#   powershell -File tools\dev.ps1            # http://localhost:8000, Daten in .\data-dev, Neustart bei Codeänderung
#   powershell -File tools\dev.ps1 -Lan       # zusätzlich im LAN erreichbar
#   powershell -File tools\dev.ps1 -Test      # Tests, Lint und Typprüfung
# Einmalig nötig: uv (winget install astral-sh.uv). Alles Weitere holt uv selbst.
param([switch]$Lan, [switch]$Test, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    "uv fehlt: winget install astral-sh.uv  (danach neues Terminal öffnen)"; exit 1
}
uv sync --group dev --group mcp
if ($Test) {
    uv run python -m pytest -q --ignore=tests/test_cad.py
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy app
    return
}
$env:LAGER_DATA_DIR = "data-dev"
$env:LAGER_BASE_URL = "http://localhost:$Port"
$env:LAGER_AUTO_BACKUP = "0"
$env:LAGER_D30 = "1"          # D30 direkt am PC (Bluetooth); "0" = aus
$hostAddr = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
Start-Job { Start-Sleep 2; Start-Process "http://localhost:$using:Port" } | Out-Null
uv run uvicorn app.main:app --reload --host $hostAddr --port $Port
