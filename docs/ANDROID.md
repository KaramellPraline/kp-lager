# Android: KP Lager als App (offline-fähig)

KP Lager ist eine installierbare Web-App (PWA). Auf Android entsteht daraus eine echte App mit Symbol,
eigenem Fenster und Offline-Speicher – ohne App-Store und ohne separate APK.

## Installieren
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
