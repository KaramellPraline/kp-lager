# Windows: Client, Server und D30-Bridge

Zielbild: der **Server** läuft als Docker-Container (`deploy/`, Dauerbetrieb). Am **Windows-PC** läuft der **Client**
(eigenes Fenster zum Server + D30-Bridge für Bluetooth-Etikettendruck). Zum **Debuggen** lässt sich der Server auch
direkt auf dem PC starten – per Installer oder mit einem Skript.

> **Status:** Skripte und Installer sind geschrieben, die Python-Teile getestet (`tests/test_m37.py`,
> `tests/test_windows_client.py`). Die `.exe`-Builds und der Bluetooth-Druck wurden noch **nicht auf Windows
> ausprobiert** (Cloud-Sitzung ohne Windows/Drucker).

## 1. Server zum Debuggen (wenig Aufwand)
Ohne Installer, mit Neustart bei Codeänderungen:
```powershell
winget install astral-sh.uv          # einmalig, danach neues Terminal
powershell -File tools\dev.ps1        # http://localhost:8000, Daten in .\data-dev
powershell -File tools\dev.ps1 -Test  # Tests, Lint, Typprüfung
```
Oder als Programm: **KP-Lager-Server-Setup.exe** (Start-Menü „KP Lager Server (Debug-Konsole)“, Daten in
`%LOCALAPPDATA%\KP Lager Server\data`, Optionen `--port`, `--host 0.0.0.0`, `--data`, `--no-d30`).

## 2. Client (Frontend am PC)
**KP-Lager-Client-Setup.exe** installiert `lager-client.exe`:
- beim ersten Start wird die Server-Adresse abgefragt (z. B. `https://lager.home.lan`), gespeichert in
  `%APPDATA%\KP Lager Client\config.json`;
- öffnet den Server in einem eigenen Fenster (Edge WebView2); ohne WebView2 im Standardbrowser;
- startet die **D30-Bridge** auf `127.0.0.1:8765`. Optional beim Anmelden nur die Bridge im Hintergrund
  (`--bridge-only`, Installer-Option „Autostart“).
- Die CA des Servers (`http://lager.home.lan/ca.crt`) einmal in Windows installieren (Zertifikat → „Vertrauenswürdige
  Stammzertifizierungsstellen“), oder `--ca <Datei>` für die Bridge angeben.

## 3. D30-Bridge – so funktioniert der Druck mit Docker-Server
1. Server mit `LAGER_D30_BRIDGE=1` (in `deploy/compose.yaml` Standard) und `LAGER_D30=0` (kein Bluetooth im Container).
2. In der Oberfläche erscheinen die D30-Schalter/Knöpfe wie bisher; ihr Status kommt von der Bridge am PC.
3. „Direkt drucken“ lässt den Server die Codes an den Browser melden, der Browser ruft die Bridge auf, die Bridge holt
   die Etikettenbilder vom Server und druckt per Bluetooth; danach meldet der Browser „gedruckt“ an den Server.
4. Sicherheit: Bridge nur auf `127.0.0.1`, nur Anfragen der eingetragenen Server-Adresse, Bilder nur von diesem
   Server, höchstens 30 Etiketten je Auftrag. Ohne laufende Bridge bleibt das Etikett in der Warteschlange.

Läuft der Server selbst auf dem Windows-PC (Debug-Server mit `LAGER_D30=1`), druckt er direkt – keine Bridge nötig.

## 4. Installer bauen
```powershell
powershell -File windows\build.ps1             # beide; Inno Setup 6 (iscc.exe) für die Installer nötig
powershell -File windows\build.ps1 -Only client
```
Oder auf GitHub: Actions › „Windows-Installer“ › Run workflow – das Ergebnis liegt als Artefakt
`kp-lager-windows` (beide `.exe`) vor.
