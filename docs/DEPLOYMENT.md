# Betrieb und Deployment

Der Server läuft nur als **Docker-Container** (Compose: App + Caddy mit HTTPS) unter `https://lager.home.lan`.
Am Windows-PC gibt es keinen Server mehr, nur den Client (`docs/WINDOWS.md`). Kurzanleitung: `deploy/README.md`.

## Windows-Programme (Server und Client getrennt)

Siehe `docs/WINDOWS.md`: Client-Installer (Fenster + D30-Bridge).

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

Neue Version ziehen und `docker compose up -d --build`. Migrationen laufen beim Start.
Vorher Tests grün (siehe `docs/DEVELOPMENT.md`).
