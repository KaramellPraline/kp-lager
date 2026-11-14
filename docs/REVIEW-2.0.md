# System-Review und Plan für 2.0.0 (Stand 1.3.0, 2026-11-14)

Die gewünschte „Vollversion 1.0.0“ heißt **2.0.0**, weil `main` bereits bei 1.3.0 steht.

## Befund
| Bereich | Zustand | Problem |
|---|---|---|
| Code-Struktur | 58 Module flach in `app/`, `web.py` mit 107 Routen in einer Funktion (1993 Zeilen) | Dateinamen folgen der Entstehung (`web_lab`, `web_extra`, `web_ops`, `api_lab`), nicht dem Inhalt; schwer zu finden, wo etwas liegt |
| Hinzufügen/Bearbeiten | Anlegen: ein Formular je Typ (`/neu`). Bearbeiten: `item.html` mit rund 25 Formularen und drei getrennten Bearbeiten-Stellen (Typ-Felder, Datenblatt, „Bearbeiten“) | Zwei völlig verschiedene Bedienwege für dieselben Felder |
| Typen | 71 Typen in 11 ungleich großen Gruppen (Elektronik 16, Schutzausrüstung 1) | Lücken (Dichtungen, Federn, Antrieb, Akkus, Farben, Reinigung …), nur eine Ebene |
| Oberfläche | Seitenleiste 10 Einträge, „Mehr“ 23, Einstellungen in 2 Tabs mit allem | Zu viele gleichrangige Einträge, Einstellungen unsortiert |
| Externe Anbindung | API-Schlüssel, MQTT-Druck, A4-Netzwerkdrucker, D30, Home Assistant, externes Backup – verteilt auf Admin-Tab, „Betrieb“ und Umgebungsvariablen | Kein gemeinsamer Ort, teils nur per Env einstellbar |
| Betrieb als Dienst | Docker + Caddy, tägliches Backup, Health-Endpunkt | **Kein Login**: wer die Adresse erreicht, darf alles. Für einen gehosteten Dienst nicht tragbar |

## Plan 2.0.0 (vier Arbeitspakete)
1. **Struktur** – `app/web/` und `app/api/` als Pakete, Routen nach Bereich (Bestand, Hinzufügen, Drucken, Einkauf, Werkstatt, System); reines Umsortieren, Verhalten und Tests unverändert.
2. **Typen** – Katalog auf zwei Ebenen (Bereich › Gruppe › Typ), rund 40 neue Typen, Schlüssel bestehender Typen bleiben.
3. **Dienst + Anbindungen** – Login (Passwort, Sitzung, Sperre nach Fehlversuchen), API bleibt über Schlüssel; Einstellungen in Reitern, neuer Reiter „Anbindungen“ für alles Externe.
4. **Hinzufügen = Bearbeiten, aufgeräumte Oberfläche** – ein gemeinsames Formular für Anlegen und Bearbeiten (Teile und Behälter), Teil-Seite als klare Ansicht mit gruppierten Aktionen, schlankere Navigation.

Reihenfolge: 1 und 2 parallel, danach 3, danach 4. Jedes Paket endet mit grünen Tests, Lint und Typprüfung.
