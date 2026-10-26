# Deployment mit Docker

> **Status:** Dateien fertig, **noch auf keinem Server gebaut/getestet**. Zielhost noch offen (kp-pi3 verworfen).
> Hostname in den QR-Codes: `lager.home.lan` (`LAGER_HOST`). Später ändern = Etiketten neu drucken.

## 1. DNS (AdGuard Home)
In AdGuard › Filter › DNS-Umschreibungen: `lager.home.lan` → IP des Docker-Hosts.
Hinweis 2026-10-26: Clients nutzen 192.168.74.90 als DNS, dort antwortet derzeit nichts (alter Pi offline).

## 2. Starten (auf dem Docker-Host)
```bash
git clone <repo> kp-lager   # oder: git archive main | ssh host 'tar -x -C kp-lager'
cd kp-lager/deploy
docker compose up -d --build
docker compose logs -f app
```
Optional `.env` neben `compose.yaml`: `LAGER_HOST=lager.home.lan`, `LAGER_WHISPER_URL=http://<host>:8001`.
Daten liegen in `deploy/data/` (SQLite + Fotos).

## 3. Handy einrichten (einmalig)
1. `http://lager.home.lan/ca.crt` öffnen → Zertifikat laden.
2. **Android:** Einstellungen › Sicherheit › Verschlüsselung & Anmeldedaten › Zertifikat installieren › CA-Zertifikat.
   **iPhone:** Profil installieren, dann Einstellungen › Allgemein › Info › Zertifikatsvertrauenseinstellungen › Vertrauen.
3. `https://lager.home.lan` öffnen → Teilen › „Zum Home-Bildschirm“ (App-Icon „KP Lager“).
4. Kamera-Scan (`/scan`) und Mikrofon funktionieren nur über HTTPS.

## Backup
```bash
docker compose exec app python -m app.backup /data/backups 30
```
Per Cron täglich: `15 3 * * * cd /pfad/deploy && docker compose exec -T app python -m app.backup /data/backups 30`.
`deploy/data/backups` zusätzlich auf NAS sichern. Restore: Container stoppen, `lager-DATUM.db` nach `data/lager.db` kopieren, Fotos entpacken, starten.

## Update
`git pull && docker compose up -d --build` – Migrationen laufen beim Start automatisch.

## Spracheingabe (optional)
Whisper nicht auf schwacher Hardware betreiben. OpenAI-kompatiblen Dienst (z. B. speaches / faster-whisper-server)
auf einem stärkeren Host starten und `LAGER_WHISPER_URL` setzen. Ohne Dienst: Mikrofon der Handy-Tastatur nutzen.
