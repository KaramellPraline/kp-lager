# Android: KP Lager als App

Zwei Wege, beide mit Offline-Modus:

## A. APK installieren (empfohlen)
1. `KP-Lager-<Version>.apk` aus GitHub › Releases auf das Handy laden.
2. Öffnen → „Installation aus unbekannten Quellen“ für den Browser/Dateimanager einmal erlauben → Installieren.
3. Beim ersten Start die Adresse eintragen, z. B. `https://lager.home.lan` (zum Testen auch `http://192.168.x.x:8000`).
4. Das Zertifikat des Lagers einmal installieren (`http://lager.home.lan/ca.crt`, Einstellungen › Sicherheit ›
   Verschlüsselung & Anmeldedaten › Zertifikat installieren › CA-Zertifikat). Die App vertraut Nutzer-Zertifikaten.

In der App:
- **Adresse ändern:** lange auf „Zurück“ drücken, oder im Fehlerdialog „Adresse ändern“.
- **QR-Scan** fragt beim ersten Mal nach der Kamera-Berechtigung.
- **Fotos** kommen aus Kamera oder Galerie; **Downloads** (Etiketten-XLSX, Export) landen in „Downloads“.
- Links zu Shops/Datenblättern öffnen im Browser.
- **Updates:** neue APK einfach drüber installieren – Daten und Anmeldung bleiben (gleiche Signatur).

Signatur: Updates lassen sich nur über eine App mit **derselben Signatur** installieren. Der Schlüssel
liegt deshalb nie im Repo, sondern als GitHub-Secret: `ANDROID_KEYSTORE_B64` (Keystore-Datei, base64),
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` (Repo › Settings › Secrets and
variables › Actions). Fehlen die Secrets, signiert der Workflow mit einem Debug-Schlüssel – installierbar,
aber jedes Update verlangt vorher das Deinstallieren der alten App.

Eigenen Schlüssel erzeugen (einmalig, gut aufheben):
```bash
keytool -genkeypair -keystore kp-lager.keystore -alias kp-lager -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 kp-lager.keystore    # Ausgabe als ANDROID_KEYSTORE_B64 eintragen
```
Lokal signieren: `KP_KEYSTORE_FILE=… KP_KEYSTORE_PASSWORD=… KP_KEY_ALIAS=… KP_KEY_PASSWORD=… ./gradlew assembleRelease`.

Selbst bauen: `cd android && ./gradlew assembleRelease` (JDK 17+, Android-SDK; Ergebnis in
`android/app/build/outputs/apk/release/`). Testbau auf GitHub: Actions › „Android-APK“.

## B. Ohne APK: Web-App installieren
1. Einmalig die CA des Servers installieren (`http://lager.home.lan/ca.crt`, siehe `deploy/README.md`).
   Ohne vertrauenswürdiges HTTPS bietet Chrome keine Installation und keinen Offline-Modus an.
2. In **Chrome** `https://lager.home.lan` öffnen → Menü ⋮ → **App installieren** (oder „Zum Startbildschirm“).
3. Die App startet danach wie jede andere App; langer Druck auf das Symbol zeigt Scannen, Hinzufügen, Suche.

## Offline
- Seiten, die einmal geöffnet wurden (Behälter, Teile, Startseite, Scannen), sind ohne Netz lesbar
  – mit dem Stand vom letzten Öffnen. Oben erscheint „offline“.
- Ohne Netz werden **Entnehmen, +/−, Einlagern, Umlagern, Inventur, Einsammeln, Etikett vormerken**
  gemerkt. Ein Hinweis zeigt, wie viele Buchungen warten. Sie werden in derselben Reihenfolge gesendet,
  sobald das Lager wieder erreichbar ist (automatisch, auch im Hintergrund, soweit Android das erlaubt).
- Nicht offline: Anlegen mit Foto, Etikettendruck, Suche über noch nie geöffnete Inhalte.
- Lehnt der Server eine gemerkte Buchung ab (z. B. Teil inzwischen gelöscht), wird sie verworfen.

## Eigene APK (optional)
Wer eine APK-Datei möchte (z. B. für Geräte ohne Chrome-Installation), kann die PWA mit
[Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap) als Trusted Web Activity verpacken:
`bubblewrap init --manifest https://lager.home.lan/manifest.webmanifest`. Voraussetzung ist ein Zertifikat,
dem das Gerät vertraut. Die App bleibt dieselbe; die PWA-Installation reicht im Normalfall.
