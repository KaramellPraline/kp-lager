# Betrieb und Deployment

Der Dauerbetrieb läuft derzeit auf dem Windows-PC KP-DESKTOP (192.168.74.5) unter `https://lager.home.lan`.
Ein Umzug auf Docker/Raspberry Pi ist vorbereitet (`Dockerfile`, `deploy/`).

## Windows-PC (aktuell)

```powershell
powershell -File tools\serve.ps1          # starten bzw. neu starten
powershell -File tools\serve.ps1 -Stop    # beenden
```

- Startet zwei Prozesse: Port 443 (App mit HTTPS) und Port 80 (`/ca.crt` für das Handy, sonst Umleitung auf HTTPS).
- Zertifikat: `uv run python tools/devcert.py lager.home.lan localhost --ip <IP>` (lokale CA, wird beim ersten Start erzeugt, liegt in `data/certs/`).
- Logs: `data/logs/https.log`, `data/logs/http.log`.
- Umgebung: `LAGER_DATA_DIR=data`, `LAGER_BASE_URL=https://lager.home.lan`.
- `tools/serve.ps1` muss als UTF-8 **mit BOM** gespeichert sein (Windows PowerShell 5.1).
- Autostart nach Neustart ist **nicht** eingerichtet (nur mit ausdrücklichem OK; geplanter Task).
- DNS: `lager.home.lan` → IP des Servers (AdGuard Home, DNS-Umschreibung).
- D30-Direktdruck: Bluetooth des Server-PCs, Drucker eingeschaltet und gekoppelt, Handy-App geschlossen (siehe `docs/DIREKTDRUCK.md`).

## Windows-Programme (Server und Client getrennt)

Siehe `docs/WINDOWS.md`: zwei Installer (Server zum Debuggen, Client mit D30-Bridge) und `tools/dev.ps1`.

## Handy einrichten (einmalig)

1. `http://lager.home.lan/ca.crt` öffnen und das Zertifikat installieren (Android: Einstellungen → Sicherheit → Zertifikat installieren → CA; iPhone: Profil + Zertifikatsvertrauen).
2. `https://lager.home.lan` öffnen → „Zum Home-Bildschirm“.
3. Kamera-Scan (`/scan`) braucht HTTPS.

## Docker (Raspberry Pi oder anderer Host)

```bash
git clone <repo-url> kp-lager && cd kp-lager/deploy
docker compose up -d --build
docker compose logs -f app
```

Details, `.env`, DNS und Backup: [deploy/README.md](../deploy/README.md). Das Image läuft auf amd64 und arm64.

**Raspberry Pi – Empfehlung:** Pi 5 mit 4 GB reicht (App + SQLite + Caddy ≈ 100–200 MB RAM); Pi 4 mit 2 GB geht ebenfalls.
Lokale KI/Whisper bleibt auf dem PC, der Pi ruft sie über das LAN auf (`LAGER_WHISPER_URL`). SSD oder gute SD-Karte verwenden
(SQLite schreibt viel) und das Backup zusätzlich auf ein zweites Medium legen. Bluetooth-Direktdruck am Pi nur mit Adapter in
Reichweite des Druckers (nur BLE; der COM-Weg ist Windows-spezifisch).

## Backup und Wiederherstellung

- Automatisch täglich (`app/scheduler.py`) nach `data/backups/` (SQLite-Kopie + Foto-Archiv, Aufbewahrung in Einstellungen).
- Manuell: Statusseite → „Backup erstellen“ oder `python -m app.backup [ziel] [tage]`.
- Wiederherstellen: App stoppen, `lager.db` (und `photos/`) aus dem Backup nach `LAGER_DATA_DIR` kopieren, App starten (Migrationen laufen automatisch).
- Umzug auf einen anderen Host = `data/` kopieren.

## Updates einspielen

`git pull`, dann App neu starten (`serve.ps1` bzw. `docker compose up -d --build`). Migrationen laufen beim Start.
Vorher Tests grün (siehe `docs/DEVELOPMENT.md`).
