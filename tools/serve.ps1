# KP Lager auf diesem Windows-PC starten – läuft unabhängig im Hintergrund weiter.
#   powershell -File tools\serve.ps1          starten (bzw. neu starten)
#   powershell -File tools\serve.ps1 -Stop    beenden
# Port 443: App mit HTTPS (https://lager.home.lan); Port 80: /ca.crt fürs Handy, sonst Umleitung.
# Logs: data\logs\https.log und data\logs\http.log
param([switch]$Stop)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

foreach ($port in 80, 443) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
if ($Stop) { "KP Lager gestoppt."; return }

if (-not (Test-Path ".venv\Scripts\python.exe")) { uv sync -q }
if (-not (Test-Path "data\certs\server.crt")) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like "192.168.*" } |
        Select-Object -First 1).IPAddress
    uv run python tools\devcert.py lager.home.lan localhost --ip $ip
}
New-Item -ItemType Directory -Force data\logs | Out-Null
$py = (Resolve-Path ".venv\Scripts\python.exe").Path
$env:LAGER_DATA_DIR = "data"
$env:LAGER_BASE_URL = "https://lager.home.lan"
# Spracheingabe über das KI-Gateway auf diesem PC (localhost -> kein Token nötig)
$env:LAGER_WHISPER_URL = "http://127.0.0.1:8766"

$env:LAGER_HTTPS_REDIRECT = ""
Start-Process -FilePath $py -WindowStyle Hidden -WorkingDirectory (Get-Location) `
    -RedirectStandardError "data\logs\https.log" -RedirectStandardOutput "data\logs\https.out.log" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "443",
                  "--ssl-keyfile", "data\certs\server.key", "--ssl-certfile", "data\certs\server.crt"
$env:LAGER_HTTPS_REDIRECT = "1"
Start-Process -FilePath $py -WindowStyle Hidden -WorkingDirectory (Get-Location) `
    -RedirectStandardError "data\logs\http.log" -RedirectStandardOutput "data\logs\http.out.log" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if ((Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue) -and
        (Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue)) {
        "KP Lager läuft: https://lager.home.lan  (Zertifikat fürs Handy: http://lager.home.lan/ca.crt)"
        return
    }
}
"Start fehlgeschlagen – siehe data\logs\https.log / http.log"
exit 1
