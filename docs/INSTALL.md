# Installation

Drei Teile, getrennt nutzbar: **Server** (Docker, Dauerbetrieb) · **Windows-Client** (Fenster + D30-Bridge am PC) ·
**Handy** (Android-App oder Browser). Aktuelle Version und Downloads: GitHub › Releases.

## 1. Server (Docker)
**Minimal:** den Ordner `deploy/handoff/` auf den Docker-Host kopieren und dort `docker compose up -d` – siehe dessen `README.md`.

Ausführlich:
Voraussetzung: Docker mit Compose auf dem Server (Raspberry Pi, NAS, Mini-PC).
```bash
git clone https://github.com/KaramellPraline/kp-lager.git && cd kp-lager/deploy
docker compose up -d --build          # baut das Image selbst
```
**Mit Release-Version statt Selbstbauen** (schneller, nachvollziehbar):
```bash
echo "LAGER_VERSION=0.2.0" >> .env      # gewünschte Version
echo "LAGER_HOST=lager.home.lan" >> .env
docker login ghcr.io -u <github-name>   # Token mit Recht read:packages (Repo ist privat)
docker compose pull && docker compose up -d
```
Daten liegen in `deploy/data/` (SQLite, Fotos, Backups). Weiteres: `deploy/README.md` (DNS, Zertifikat, externes Backup).

**Aktualisieren:** `LAGER_VERSION` auf die neue Nummer setzen, `docker compose pull && docker compose up -d`.
Datenbank-Migrationen laufen beim Start automatisch; vorher ein Backup (`docker compose exec app python -m app.backup /data/backups 30`).
**Zurück zur alten Version:** `LAGER_VERSION` zurücksetzen und neu starten (Backup einspielen, falls die Migration schon lief).

## 2. Windows-Client
1. `KP-Lager-Client-Setup-<Version>.exe` aus dem Release laden und ausführen (kein Administrator nötig).
2. Beim ersten Start die Server-Adresse eintragen, z. B. `https://lager.home.lan`.
3. Zertifikat des Servers (`http://lager.home.lan/ca.crt`) in Windows als vertrauenswürdige Stammzertifizierungsstelle installieren.
4. Für D30-Druck: Bluetooth am PC, D30 einschalten und koppeln. Details: `docs/WINDOWS.md`.

## 3. Debuggen am PC (optional)
Kein Windows-Server mehr: zum Entwickeln `uv run uvicorn app.main:app --reload` (siehe `docs/DEVELOPMENT.md`). Etiketten tragen trotzdem immer `https://lager.home.lan`.

## 4. Handy (Android)
`KP-Lager-<Version>.apk` aus dem Release installieren, Adresse eintragen, CA-Zertifikat installieren – Details in `docs/ANDROID.md`.
Ohne APK (auch iPhone): `https://lager.home.lan` öffnen, CA installieren, „Zum Home-Bildschirm“.

## Version prüfen
Mehr › Status zeigt die Version des Servers; `https://<host>/health` liefert sie als JSON; `lager-client.exe --version`.
