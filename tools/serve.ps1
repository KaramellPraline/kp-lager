# KP Lager lokal mit HTTPS starten (Windows). Aufruf: powershell -File tools\serve.ps1
# Port 443: App mit HTTPS; Port 80: /ca.crt fürs Handy, sonst Umleitung auf HTTPS.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like "192.168.*" } | Select-Object -First 1).IPAddress
if (-not (Test-Path "data\certs\server.crt")) { uv run python tools\devcert.py lager.home.lan localhost --ip $ip }
$env:LAGER_DATA_DIR = "data"
$env:LAGER_BASE_URL = "https://lager.home.lan"
Start-Process -NoNewWindow uv -ArgumentList "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "443", "--ssl-keyfile", "data\certs\server.key", "--ssl-certfile", "data\certs\server.crt"
$env:LAGER_HTTPS_REDIRECT = "1"
uv run uvicorn app.main:app --host 0.0.0.0 --port 80
