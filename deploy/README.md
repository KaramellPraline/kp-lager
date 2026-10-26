# Deployment (Proxmox-LXC)

> **Vor dem Etikettendruck festlegen:** Der Hostname steht in jedem QR-Code (`https://<host>/c/0042`). Später ändern = neu drucken.

## 1. Hostname im LAN wählen
- **Fritz!Box:** Container-Hostname `lager` → automatisch `lager.fritz.box`. Dann `LAGER_HOST=lager.fritz.box`.
- **Pi-hole/AdGuard/Router mit lokalem DNS:** Eintrag `lager.home.arpa` → IP des Containers (`.home.arpa` ist der offizielle Heimnetz-Suffix).
- Container-IP im Router fest vergeben (DHCP-Reservierung).

## 2. Container anlegen (Proxmox-Shell)
Debian-13-Template, 1 CPU, 512 MB RAM, 4 GB Disk reichen (Whisper später: 2 CPU, 2 GB RAM). Unprivilegiert, Hostname `lager`, Onboot an.

## 3. Code übertragen (vom Windows-PC, Git Bash)
```bash
cd /c/dev/sortiersystem
git archive --format=tar.gz -o /tmp/lager.tgz main
scp /tmp/lager.tgz root@<container-ip>:/tmp/
ssh root@<container-ip> 'mkdir -p /opt/sortiersystem && tar -xzf /tmp/lager.tgz -C /opt/sortiersystem'
```

## 4. Installieren (im Container)
```bash
LAGER_HOST=lager.fritz.box BACKUP_DIR=/mnt/backup bash /opt/sortiersystem/deploy/install.sh
```
`BACKUP_DIR` idealerweise ein per Proxmox eingehängtes NAS-Verzeichnis (Mountpoint `mp0`). Zusätzlich Proxmox-vzdump des Containers einplanen.

## 5. Handy einrichten (einmalig)
1. `http://<host>/ca.crt` im Handy-Browser öffnen → Zertifikat laden.
2. **Android:** Einstellungen › Sicherheit › Verschlüsselung & Anmeldedaten › Zertifikat installieren › CA-Zertifikat.
   **iPhone:** Profil installieren (Einstellungen › Profil geladen), dann Einstellungen › Allgemein › Info › Zertifikatsvertrauenseinstellungen › Vertrauen einschalten.
3. `https://<host>` öffnen → kein Warnhinweis mehr. Zum Startbildschirm hinzufügen.
4. QR-Codes mit der normalen Kamera-App scannen.

## Update
Schritt 3 wiederholen, dann im Container:
```bash
chown -R lager:lager /opt/sortiersystem && sudo -u lager env UV_PYTHON_INSTALL_DIR=/var/lib/sortiersystem/python UV_CACHE_DIR=/var/lib/sortiersystem/.cache uv sync --project /opt/sortiersystem --no-dev --frozen && systemctl restart sortiersystem
```
Datenbank-Migrationen laufen beim Start automatisch.

## Backup / Restore
- Täglich 03:15: `lager-JJJJ-MM-TT.db` + `photos-JJJJ-MM-TT.tar.gz` in `BACKUP_DIR`, 30 Tage. Manuell: `systemctl start sortiersystem-backup`.
- Restore: `systemctl stop sortiersystem`, Datei nach `/var/lib/sortiersystem/lager.db` kopieren, Fotos entpacken, `chown -R lager:lager /var/lib/sortiersystem`, starten.

## Notbetrieb auf Raspberry Pi 2B
Gleiche Schritte auf Raspberry Pi OS Lite (32 bit) – ungetestet. Kern läuft, Whisper/Embeddings nicht vorsehen.
