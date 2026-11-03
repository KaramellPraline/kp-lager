# Konfiguration

## Umgebungsvariablen (Server)

| Variable | Standard | Bedeutung |
|---|---|---|
| `LAGER_DATA_DIR` | `data` | Ablage für SQLite (`lager.db`), Fotos, Datenblätter, Backups, Notizen, Zertifikate |
| `LAGER_BASE_URL` | `https://lager.home.lan` | Adresse, die in die QR-Codes kommt (später ändern = Etiketten neu drucken) |
| `LAGER_WHISPER_URL` | leer | KI-Gateway für Spracheingabe (OpenAI-kompatibel, z. B. `http://127.0.0.1:8766`); leer = aus |
| `LAGER_WHISPER_TOKEN` | `local` | Bearer-Token für das Gateway |
| `LAGER_AI_URL` | wie `LAGER_WHISPER_URL` | Chat-/Vision-Gateway (Teil ausfüllen, Foto-Erkennung) |
| `LAGER_AUTO_BACKUP` | `1` | tägliches Backup im Hintergrund (`0` in Tests/Entwicklung) |
| `LAGER_D30` | `1` | D30-Direktdruck per Bluetooth anbieten (`0` = Checkbox/Knöpfe verschwinden) |
| `LAGER_D30_PORT` | automatisch | erzwingt den Bluetooth-Seriell-Port (z. B. `COM5`) |
| `LAGER_D30_ADDR` | – | Bluetooth-Adresse (z. B. `E2B733D33FE0`), falls mehrere Ports gefunden werden |
| `LAGER_HTTPS_REDIRECT` | leer | `1` = HTTP-Instanz (Port 80): nur `/ca.crt`, sonst Umleitung auf HTTPS |

## Umgebungsvariablen (Client-Tools)

| Variable | Bedeutung |
|---|---|
| `LAGER_URL` | Adresse der App für CLI/MCP (Standard `https://lager.home.lan`) |
| `LAGER_API_KEY` | Schlüssel für Schreibzugriff über API/CLI/MCP (in der App: Einstellungen → Admin → API-Schlüssel) |
| `LAGER_CA` | Pfad zur CA-Datei, falls die App ein selbst signiertes Zertifikat nutzt |

Geheimnisse nie committen. Die Datei `.env` ist in `.gitignore`.

## Einstellungen in der App (`/settings`)

Werte liegen in der Tabelle `meta` (Register: `app/prefs.py`). Dazu gehören Design/Theme, Startseiten-Abschnitte,
Code-Zähler je Präfix, Backup-Aufbewahrung (`backup_days`), Slicer-Ordner, KI-Modelle, Etikettenformat u. a.
Neue Einstellungen werden nur im Register ergänzt; die Seite wird daraus erzeugt.

## Code-Schema

`PRÄFIX-NNN` (z. B. `EUR-001`, `CNS-014`, `BIN-007`, `MAS-001`, `TRO-001`). Präfixe: siehe `/codes` in der App und
`docs/ETIKETTEN.md`. Behälterarten sind erweiterbar (Tabelle `container_kind`).
