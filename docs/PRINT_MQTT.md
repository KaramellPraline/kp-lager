# Etikettendruck über MQTT

Der Server (z. B. auf dem Pi) hat kein Bluetooth. Der **Druck-Agent** (`app/print_agent.py`) läuft auf dem PC mit dem D30, nimmt Aufträge vom MQTT-Broker an und druckt sie (`app/d30.py`). KP Lager und jedes andere Programm im LAN können so Etiketten einreihen.

## Einrichtung (kp-network, vom Desktop)
`.\scripts\local\deploy_printer.ps1 [-Autostart]` legt die MQTT-Benutzer `kp-lager` und `kp-desktop-print` an, setzt die ACL, konfiguriert KP Lager auf dem Pi (`LAGER_PRINT_MQTT*`, Passwort nur in `/home/admin/kp-lager/.env`) und startet den Agenten (Log: `%LOCALAPPDATA%\kp-print-agent.log`). Der Server braucht `LAGER_D30=1`.

Server-Umgebung: `LAGER_PRINT_MQTT=host[:port]`, `LAGER_PRINT_MQTT_USER`, `LAGER_PRINT_MQTT_PASSWORD` (oder `..._PASSWORD_FILE`). Ist `LAGER_PRINT_MQTT` gesetzt, gehen alle Druckknöpfe (Warteschlange, Hinzufügen, Sammeldruck) über MQTT.

Agent von Hand: `python -m app.print_agent --broker 192.168.74.6 --password-file <Datei>` (`--dry-run` druckt nicht, meldet aber Erfolg).

## Themen
| Thema | Richtung | Inhalt |
|---|---|---|
| `print/d30/queue` | Programm → Agent | Auftrag (JSON) |
| `print/d30/result` | Agent → Programm | `{"id","ok":true,"printed":N}` oder `{"id","ok":false,"error":"…"}` |
| `print/d30/status` | Agent → alle (retained) | `{"online":true,"available":<D30 erreichbar>,"msg":""}`; offline per Last Will `{"online":false}` |

## Auftrag
Entweder fertige Bilder (PNG, base64, 320×96 px, wird sonst skaliert):
```json
{"id": "abc123", "app": "meine-app", "images": ["iVBORw0KGgo…"]}
```
oder Etiketten, die der Agent selbst zeichnet (Text, kleine Zeile, QR-Inhalt):
```json
{"id": "abc124", "app": "meine-app", "labels": [{"text": "Netzteil 12V", "extra": "Regal 2", "qr": "https://lager.home.lan/c/ART-0001"}]}
```
Höchstens 30 Etiketten je Auftrag, Bilder bis 200 KB. `id` frei wählen (kommt im Ergebnis zurück). Aufträge laufen nacheinander. Der Agent muss online sein, sonst bricht der Server den Druck mit einer Meldung ab (nichts wird als gedruckt gebucht). Beispiel:
`mosquitto_pub -h 192.168.74.6 -u <benutzer> -P <pw> -t print/d30/queue -m '{"id":"t1","labels":[{"text":"Test"}]}'`

## Rechte (Mosquitto-ACL in kp-network)
Jedes Gerät darf `print/d30/queue` schreiben und `result`/`status` lesen; nur `kp-desktop-print` liest die Warteschlange und schreibt Ergebnis/Status.
