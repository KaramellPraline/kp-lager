# Konfiguration

## Umgebungsvariablen (Server)

| Variable | Standard | Bedeutung |
|---|---|---|
| `LAGER_DATA_DIR` | `data` | Ablage für SQLite (`lager.db`), Fotos, Datenblätter, Backups, Notizen, Zertifikate |
| `LAGER_BASE_URL` | `https://lager.home.lan` | Adresse, die in die QR-Codes kommt (später ändern = Etiketten neu drucken) |
| `LAGER_AUTO_BACKUP` | `1` | tägliches Backup im Hintergrund (`0` in Tests/Entwicklung) |
| `LAGER_D30` | `1` | D30-Direktdruck per Bluetooth anbieten (`0` = Checkbox/Knöpfe verschwinden) |
| `LAGER_D30_PORT` | automatisch | erzwingt den Bluetooth-Seriell-Port (z. B. `COM5`) |
| `LAGER_D30_ADDR` | – | Bluetooth-Adresse (z. B. `E2B733D33FE0`), falls mehrere Ports gefunden werden |
| `LAGER_HTTPS_REDIRECT` | leer | `1` = HTTP-Instanz (Port 80): nur `/ca.crt`, sonst Umleitung auf HTTPS |
| `LAGER_AUTH` | `1` | Anmeldung (Login) an; `0` = aus (reines Heimnetz, jeder im Netz darf alles). Modell: `docs/SICHERHEIT.md` |
| `LAGER_ADMIN_USER` | – | legt beim Start diesen Admin an, falls noch kein Benutzer existiert (sonst: `/einrichten` im Browser) |
| `LAGER_ADMIN_PASSWORD_FILE` | – | Datei mit dessen Passwort (Docker-Secret, z. B. `/run/secrets/lager_admin`) |
| `LAGER_D30_BRIDGE` | – | `1`/`0` erzwingt die D30-PC-Bridge; ungesetzt = Schalter unter Einstellungen › Anbindungen › Druck |
| `LAGER_PRINT_MQTT` | – | MQTT-Druck: `host[:port]`; dazu `LAGER_PRINT_MQTT_USER`, `LAGER_PRINT_MQTT_PASSWORD` (oder `…_PASSWORD_FILE`), `LAGER_PRINT_MQTT_TOPIC` (Standard `print/d30`). Hat Vorrang vor Anbindungen › Druck |
| `LAGER_BACKUP_EXTERN` | – | Zielordner für das externe Backup, falls unter Anbindungen › Backup extern nichts eingetragen ist |

## Umgebungsvariablen (Client-Tools)

| Variable | Bedeutung |
|---|---|
| `LAGER_URL` | Adresse der App für CLI/MCP (Standard `https://lager.home.lan`) |
| `LAGER_API_KEY` | Schlüssel für Schreibzugriff über API/CLI/MCP (in der App: Einstellungen › Anbindungen › API &amp; Schlüssel) |
| `LAGER_CA` | Pfad zur CA-Datei, falls die App ein selbst signiertes Zertifikat nutzt |

Geheimnisse nie committen. Die Datei `.env` ist in `.gitignore`.

## Einstellungen in der App (`/settings`)

Reiter: **Allgemein** (Name, Design, Startseite) · **Bedienung** (Erfassung, Etiketten, Sortierkästen, Suche) ·
**Anbindungen** (API &amp; Schlüssel, MCP, Home Assistant, Druck: A4/IPP, MQTT, D30-Bridge, Backup extern – je mit
Status und „Testen“) · **Benutzer** (eigenes Passwort, Benutzerverwaltung, Sitzungsdauer) · **System** (Backup-Aufbewahrung,
Inventur, Slicer-Ordner, Daten, Nummernvergabe, Node-Typen). `/settings/admin` leitet auf System weiter.
Geheimnisse (MQTT-Passwort) liegen als `secret:*` in `meta`, werden nie wieder angezeigt und nicht exportiert.

Werte liegen in der Tabelle `meta` (Register: `app/prefs.py`, Reiter-Zuordnung `prefs.TABS`). Dazu gehören Design/Theme, Startseiten-Abschnitte,
Code-Zähler je Präfix, Backup-Aufbewahrung (`backup_days`), Slicer-Ordner, Etikettenformat u. a.
Neue Einstellungen werden nur im Register ergänzt; die Seite wird daraus erzeugt.

## Code-Schema

`PRÄFIX-NNN` (z. B. `EUR-001`, `CNS-014`, `BIN-007`, `MAS-001`, `TRO-001`). Präfixe: siehe `/codes` in der App und
`docs/ETIKETTEN.md`. Behälterarten sind erweiterbar (Tabelle `container_kind`).
