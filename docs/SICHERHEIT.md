# Sicherheit (Stand 2.0, Arbeitspaket 3)

KP Lager kann als gehosteter Dienst laufen. Dafür gibt es eine schlanke Anmeldung ohne Zusatzpakete
(`app/auth.py`, Middleware `app/web/guard.py`). Standard: **an** (`LAGER_AUTH=1`).

## Was ist geschützt – und wie
| Bereich | Schutz |
|---|---|
| Oberfläche (alle Seiten, HTMX, Fotos `/photos`, Datenblätter `/datasheets`, Exporte) | Sitzung per Cookie; ohne Sitzung: Seiten → `/login?next=…`, HTMX → 401 + `HX-Redirect`, `fetch`/Service Worker → 401 JSON |
| Einstellungen, Anbindungen, Benutzerverwaltung, Import, Gesamtarchiv `/export.zip` | nur Rolle **Admin** (Nutzer: 403); das eigene Passwort ändern darf jeder (`/settings/benutzer`) |
| Schreibende Anfragen der Oberfläche (POST/PUT/PATCH/DELETE) | Herkunftsprüfung: `Origin` muss zum eigenen Host passen (auch mit `LAGER_AUTH=0`), dazu Cookie `SameSite=Lax` |
| REST `/api/v1` | unverändert: eigene Schlüssel (`X-API-Key`), Lesen offen oder per Einstellung nur mit Schlüssel |
| Etikettenbild `/labels/img/<CODE>.png` | Sitzung, signierter Kurzlink (`?t=`, 15 min, je Code; für die D30-PC-Bridge) oder API-Schlüssel |

Ohne Anmeldung erreichbar: `/health`, `/ca.crt`, `/static/*`, `/sw.js`, `/manifest.webmanifest`, `/offline`,
`/login`, `/einrichten` (nur solange es keinen Benutzer gibt) und `/api/v1/*`.

## Einzelheiten
- **Passwörter:** `hashlib.scrypt` (n=2^14, r=8, p=1) mit 16 Byte Salt je Passwort; mindestens 8 Zeichen.
- **Sitzungen:** 32 Byte Zufall (`secrets`) im Cookie `lager_session` (`HttpOnly`, `SameSite=Lax`, `Secure`, wenn die
  Anfrage per HTTPS kam – auch hinter Caddy über `X-Forwarded-Proto`). In der Datenbank steht nur der SHA-256.
  Laufzeit gleitend (Einstellungen › Benutzer, Standard 30 Tage). Abmelden löscht die Sitzung; ein neues Passwort
  beendet alle anderen Sitzungen des Benutzers.
- **Sperre:** 5 Fehlversuche je Benutzername und Adresse (bzw. 20 je Adresse über alle Namen) → 10 Minuten gesperrt.
  Unbekannte Namen bekommen dieselbe Meldung und dieselbe Rechenzeit (Vergleich mit einem Dummy-Hash) –
  kein Benutzer-Aufzählen. Die Adresse kommt hinter Caddy aus `X-Forwarded-For` (uvicorn `--proxy-headers`).
- **Erster Start:** ohne Benutzer leitet jede Seite auf `/einrichten` (Admin anlegen). Oder per Umgebung
  `LAGER_ADMIN_USER` + `LAGER_ADMIN_PASSWORD_FILE` (Docker-Secret); das Passwort steht nie in der Umgebung oder im Log.
- **Letzter Admin:** kann weder gelöscht noch zum Nutzer gemacht werden.
- **Rücksprung:** `?next=` nimmt nur relative Pfade (`/…`, kein `//host`, kein Schema, kein Backslash).
- **Geheimnisse der Anbindungen** (MQTT-Passwort) liegen als `secret:*` in `meta`: nie wieder angezeigt (nur „gesetzt“),
  nicht im JSON-Export, nicht im Log. Umgebungsvariablen haben Vorrang.

## Entscheidung CSRF: Origin-Prüfung statt Formular-Token
Die Oberfläche hat sehr viele Formulare, HTMX-Knöpfe und `fetch`-Aufrufe; dazu speichert der Service Worker Seiten
für die Offline-Nutzung und sendet gemerkte Buchungen später erneut. Ein Token je Sitzung müsste in jedes Formular und
wäre in offline gespeicherten Seiten und gemerkten Buchungen veraltet. Stattdessen:
1. Cookie `SameSite=Lax`: Browser schicken es bei POSTs von fremden Seiten nicht mit.
2. Jede schreibende Anfrage mit `Origin`-Kopfzeile, deren Host nicht der eigene ist (oder `Origin: null`), wird mit 403
   abgelehnt. Aktuelle Browser setzen `Origin` bei jedem POST, `fetch` und HTMX-Aufruf – auch im Service Worker.
3. Ohne `Origin` (Werkzeuge, Tests, sehr alte Browser) wird zugelassen; dort greift Punkt 1.

Damit ist auch die Variante ohne Login (`LAGER_AUTH=0`) gegen „fremde Webseite steuert den Browser im LAN fern“ geschützt.

## Was NICHT geschützt ist (bewusst)
- **`LAGER_AUTH=0`:** jeder, der die Adresse erreicht, darf alles (nur fürs reine Heimnetz).
- **API-Lesen** ist standardmäßig ohne Schlüssel offen (wie bisher). Ist das Lager von außen erreichbar:
  Einstellungen › Anbindungen › API › „Auch Lesen nur mit Schlüssel“ einschalten (die Karte warnt).
- **Transport:** HTTPS macht Caddy (eigene CA). Ohne HTTPS gehen Passwort und Cookie im Klartext durchs Netz.
- **Gesamtarchiv/Backups** enthalten die Datenbank mit Passwort-Hashes und gespeicherten Geheimnissen – wie die
  Datei `data/lager.db` selbst sicher aufbewahren. Eine wiederhergestellte alte Datenbank ohne Benutzer führt zu `/einrichten`.
- Kein Zwei-Faktor, keine Passwort-Zurücksetzung per Mail (Admin setzt es; Notfall: `docs/DEPLOYMENT.md`).
- Etikettenbilder sind mit gültigem Kurzlink 15 Minuten ohne Sitzung abrufbar (nur Name und Code des Etiketts).

## Clients
- **Android-App:** WebView mit dauerhaften Cookies (`CookieManager`), Downloads senden das Cookie mit – nichts zu tun.
- **Windows-Client:** pywebview ohne privaten Modus (Profil `%APPDATA%\KP Lager Client\webview`), damit die Anmeldung
  Neustarts übersteht. Die D30-Bridge nutzt die signierten Kurzlinks.
- **Offline-App (`sw.js`):** speichert nie die Login-Seite als Offline-Fassung (`Cache-Control: no-store`,
  `X-Lager-Login`); gemerkte Buchungen, die mit 401/403 oder Umleitung auf `/login` beantwortet werden, bleiben in der
  Warteschlange und gehen nach dem nächsten Login raus.
