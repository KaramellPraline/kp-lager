# Deployment mit Docker

> **Minimal-Übergabe:** der Ordner `deploy/handoff/` (3 Dateien + Kurzanleitung) genügt für den Betrieb – ohne den Rest des Repos.

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
Optional `.env` neben `compose.yaml`: `LAGER_HOST=lager.home.lan`, `LAGER_BACKUP_HOST_DIR=/mnt/nas/lager`
(Host-Ordner für das externe Backup, siehe unten) und `LAGER_D30_BRIDGE=1` (Standard; Etiketten drucken über den Windows-Client).
Daten liegen in `deploy/data/` (SQLite + Fotos).

## 3. Handy einrichten (einmalig)
1. `http://lager.home.lan/ca.crt` öffnen → Zertifikat laden.
2. **Android:** Einstellungen › Sicherheit › Verschlüsselung & Anmeldedaten › Zertifikat installieren › CA-Zertifikat.
   **iPhone:** Profil installieren, dann Einstellungen › Allgemein › Info › Zertifikatsvertrauenseinstellungen › Vertrauen.
3. `https://lager.home.lan` öffnen → Teilen › „Zum Home-Bildschirm“ (App-Icon „KP Lager“).
4. Kamera-Scan (`/scan`) funktioniert nur über HTTPS.

## Backup
```bash
docker compose exec app python -m app.backup /data/backups 30
```
Per Cron täglich: `15 3 * * * cd /pfad/deploy && docker compose exec -T app python -m app.backup /data/backups 30`.
Externes Backup: in `.env` `LAGER_BACKUP_HOST_DIR` auf einen NAS-/USB-Ordner des Hosts setzen und `LAGER_BACKUP_EXTERN=/backup-extern`
(oder in der App unter Einstellungen › Betrieb › „Externes Backup“ denselben Pfad `/backup-extern` eintragen). Die tägliche Sicherung wird
dann zusätzlich dorthin kopiert; Status unter Mehr › Status & Backup. Restore: Container stoppen, `lager-DATUM.db` nach `data/lager.db` kopieren, Fotos entpacken, starten.

## Update
`git pull && docker compose up -d --build` – Migrationen laufen beim Start automatisch.
