# Windows: nur der Client

Der **Server läuft ausschließlich als Docker-Container** (`deploy/`, siehe `deploy/README.md`). Am Windows-PC gibt es
nur den **Client**: ein eigenes Fenster zum Lager plus die **D30-Bridge** für den Bluetooth-Etikettendruck.

## Installieren
`KP-Lager-Client-Setup-<Version>.exe` aus dem Release (GitHub › Releases › Assets) ausführen – kein Administrator nötig.
1. Beim ersten Start die Server-Adresse eintragen, z. B. `https://lager.home.lan` (gespeichert in `%APPDATA%\KP Lager Client\config.json`).
2. Das Zertifikat des Servers (`http://lager.home.lan/ca.crt`) in Windows als vertrauenswürdige Stammzertifizierungsstelle installieren.
3. Für D30-Druck: Bluetooth am PC, D30 einschalten und koppeln.

Optionen: `--server <Adresse>`, `--bridge-only` (nur Bridge, kein Fenster), `--ca <Datei>`, `--no-bridge`, `--reset`, `--version`.
Installer-Option „Autostart“ startet beim Anmelden nur die Bridge im Hintergrund.

## D30-Bridge – so funktioniert der Druck
1. Server mit `LAGER_D30_BRIDGE=1` (in `deploy/compose.yaml` Standard) und `LAGER_D30=0` (kein Bluetooth im Container).
2. In der Oberfläche erscheinen die D30-Schalter wie gewohnt; ihr Status kommt von der Bridge am PC.
3. „Direkt drucken“ lässt den Server die Codes an den Browser melden, der Browser ruft die Bridge auf, die Bridge holt die
   Etikettenbilder vom Server und druckt per Bluetooth; danach meldet der Browser „gedruckt“ an den Server.
4. Sicherheit: Bridge nur auf `127.0.0.1`, nur Anfragen der eingetragenen Server-Adresse, Bilder nur von diesem Server,
   höchstens 30 Etiketten je Auftrag. Ohne laufende Bridge bleibt das Etikett in der Warteschlange.

## Wo liegt die .exe?
Im Repository liegen keine fertigen Programme:
- **Release:** GitHub › Releases › Version › Assets (siehe `docs/RELEASE.md`).
- **Testbau:** GitHub › Actions › „Windows-Installer“ › Lauf › **Artifacts** › `kp-lager-windows`.
- **Lokal:** `powershell -File windows\build.ps1` → `dist\installer\` (Inno Setup 6 für den Installer nötig).
