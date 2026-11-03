# KP Lager – Docker in 5 Minuten

Voraussetzung: ein Rechner im LAN mit Docker + Docker Compose (Raspberry Pi, NAS, Mini-PC).

```bash
docker login ghcr.io -u <github-name>    # einmalig; Token mit Recht read:packages (Repo ist privat)
docker compose up -d                     # in diesem Ordner
```

1. **DNS:** im Router/AdGuard `lager.home.lan` → IP dieses Rechners eintragen.
2. **Zertifikat:** `http://lager.home.lan/ca.crt` auf Handy/PC laden und installieren (einmalig).
3. **Öffnen:** `https://lager.home.lan`. QR-Codes tragen immer diese Adresse.
4. **Bestand übernehmen:** altes System → Mehr › Export (JSON), neues System → Mehr › Import › Datei › Vorschau › Übernehmen.

| Aufgabe | Befehl |
|---|---|
| Status / Logs | `docker compose ps` · `docker compose logs -f app` |
| Update | `LAGER_VERSION=0.4.0` in `.env`, dann `docker compose pull && docker compose up -d` |
| Zurück | alte Nummer in `.env`, `docker compose up -d` (vorher Backup einspielen, falls Migration lief) |
| Backup | läuft täglich automatisch nach `data/backups/`; `data/` zusätzlich kopieren (NAS/USB) |
| Stoppen | `docker compose down` (Daten bleiben in `data/`) |

Alles Wichtige liegt in `./data`. Ohne diesen Ordner gibt es keinen Bestand – nicht löschen.
