# KP Lager – Windows-Client bauen (Fenster zum Server + D30-PC-Bridge).
#   powershell -File windows\build.ps1 [-Version 0.3.0]
# Ergebnis: dist\lager-client\ und, falls Inno Setup 6 (iscc.exe) vorhanden, dist\installer\KP-Lager-Client-Setup-<Version>.exe
# Voraussetzung: uv (https://docs.astral.sh/uv/). Den Server gibt es nur als Docker-Container (deploy/).
param([string]$Version = "")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not $Version) { $Version = (Select-String -Path app\__init__.py -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value }
"KP Lager Client Version $Version"

uv run --with pyinstaller --with pywebview python -m PyInstaller --noconfirm --clean `
    --name lager-client --windowed --paths . `
    --collect-submodules bleak --collect-submodules serial --collect-submodules webview `
    --hidden-import app.d30_bridge --hidden-import tkinter `
    windows\client\kp_client.py

$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) { $iscc = $null }
}
if ($iscc) {
    New-Item -ItemType Directory -Force dist\installer | Out-Null
    & $iscc "/DAppVersion=$Version" windows\installer\client.iss
    "Installer: dist\installer\"
} else {
    "Inno Setup (iscc.exe) nicht gefunden - nur der Ordner dist\lager-client wurde gebaut."
}
