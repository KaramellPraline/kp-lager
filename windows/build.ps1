# KP Lager – Windows-Programme bauen (Server und Client getrennt).
#   powershell -File windows\build.ps1            # beide: PyInstaller + (falls Inno Setup da) Installer
#   powershell -File windows\build.ps1 -Only server|client
# Ergebnis: dist\lager-server\, dist\lager-client\ und Installer in dist\installer\
# Voraussetzung: uv (https://docs.astral.sh/uv/), optional Inno Setup 6 (iscc.exe) für die Installer.
param([ValidateSet("all", "server", "client")][string]$Only = "all")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$data = @(
    "--add-data", "app\templates;app\templates",
    "--add-data", "app\static;app\static",
    "--add-data", "app\migrations;app\migrations"
)

function Build-Server {
    uv run --with pyinstaller python -m PyInstaller --noconfirm --clean `
        --name lager-server --console --paths . @data `
        --collect-submodules uvicorn --collect-submodules bleak --collect-submodules serial `
        --hidden-import app.main `
        windows\server\kp_server.py
}

function Build-Client {
    uv run --with pyinstaller --with pywebview python -m PyInstaller --noconfirm --clean `
        --name lager-client --windowed --paths . `
        --collect-submodules bleak --collect-submodules serial --collect-submodules webview `
        --hidden-import app.d30_bridge --hidden-import tkinter `
        windows\client\kp_client.py
}

if ($Only -in "all", "server") { Build-Server }
if ($Only -in "all", "client") { Build-Client }

$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) { $iscc = $null }
}
if ($iscc) {
    New-Item -ItemType Directory -Force dist\installer | Out-Null
    if ($Only -in "all", "server") { & $iscc windows\installer\server.iss }
    if ($Only -in "all", "client") { & $iscc windows\installer\client.iss }
    "Installer: dist\installer\"
} else {
    "Inno Setup (iscc.exe) nicht gefunden - nur die Ordner in dist\ wurden gebaut."
}
