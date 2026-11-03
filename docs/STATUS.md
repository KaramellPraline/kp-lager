# Status

Stand: 2026-11-03

## Aktuell
- App „KP Lager“ läuft auf dem Windows-PC unter **https://lager.home.lan** (DNS in AdGuard auf 192.168.74.6 → 192.168.74.5). Start: `tools/serve.ps1` (443 HTTPS + 80 für `/ca.crt`).
- Neu: NORB16-Draufsicht mit Einsätzen (EIN-Codes), Schnelleingabe im Kasten, Etiketten-Warteschlange (XLSX/A8/A4 40×12), responsives Layout (Handy: untere Navigation, Desktop: Seitenleiste), Einstellungsregister (`app/prefs.py`).
- Bin-Generator `cad/norb_bins.py`: Rillen (Spitzbogen), Greifmulde R15, Innenrundungen, Etikettenablage. **Testdruck steht aus** (Passung, Rippenrichtung).
- 2026-10-27: Backlog M10–M17 umgesetzt und live (DB-Version 9). API `/api/v1` + CLI + MCP; Schlüssel in Einstellungen → Admin.
- Offen: Handy-Test (CA installieren), Probedruck D30 + QR-Scan, Bin-Testdruck, Autostart nach Neustart (nur mit OK), Docker-Host für Dauerbetrieb.

- 2026-11-03: **KI-frei + Hinzufügen-Tab**: alle KI-Bausteine entfernt; Start nur noch Bestandsbrowser; Hinzufügen (`/neu`) mit Reitern Teile · Behälter · Kabel & Material · Einsatz, untere Leiste: Bestand · Hinzufügen · Scannen · Einkauf · Etiketten.

- 2026-11-03 (M35): Einkäufe/Lieferanten, Notiz- & Pinout-Karten, Inventur, Stücklisten-Abgleich (Fehlmengen → Einkaufsliste), externes Backup (Ordner/NAS), Startseite mit Aufgaben-Karten und Kennzahlen, Mehr-Menü gruppiert, Hinzufügen merkt letzten Reiter. Migration 019.
- 2026-11-03 (M36): API mit Lese-/Schreib-Schlüsseln, `PATCH/DELETE` für Teile, Behälter anlegen/ändern, Projekte, Einkäufe, Karten, Inventur, `/overview`, `/tree`; MCP/Client erweitert (`docs/API.md`).
- 2026-11-03 (M37): Windows: Client (Fenster + D30-PC-Bridge `app/d30_bridge.py`) und Server (Debug) als getrennte Installer (`windows/`, `docs/WINDOWS.md`), `tools/dev.ps1`, Docker-Compose mit Bridge-Modus (`LAGER_D30_BRIDGE`) und externem Backup-Volume. **Offen: .exe-Build und Bluetooth-Druck auf Windows testen.**
- Offen (Oberfläche): Detail-Feinschliff nach Rückmeldung (Tabs, Menügruppen, Startseite sind umgesetzt).
- 2026-11-03 (M38): Versionsnummer (0.2.0) in Status/Health/API, `tools/release.py`, CHANGELOG.md, Release-Workflow (Tests → Windows-Installer + Docker-Image → GitHub-Release), `docs/INSTALL.md`, `docs/RELEASE.md`; Bestand mit Orte/Baum-Reitern, mehr Aufgaben-Karten, Entnehmen mit Mengen-Schnellauswahl.
- 2026-11-04 (M39): Typen am Teil (`item.ctype`/`cfields`, Migration 020): Typ-Datenblatt am Teil, Sortiment nach Typ mit Filtern und natürlicher Sortierung, Variantenraster für alle Typen inkl. Material-Profilen, Dublettenwarnung beim Anlegen, eigene Typen (`/sortiment/eigene`), Altbestand-Zuordnung per Regeln (`/sortiment/zuordnen`), API `/types/catalog`.
- 2026-11-04 (M40): Standard-Mindestbestand je Typ (Teil überschreibt), Platz-Vorschlag beim Anlegen, Zählen per Waage (Stückgewicht/Tara), Ablauf-Seite mit „Heute geöffnet“ (Haltbarkeit je Typ), Verlängern, Verbraucht.
- 2026-11-04 (M41): Projekt-Reservierung (andere Projekte sehen nur Freies, Einsammeln/Erledigt gibt frei), Einkauf aus CSV, Rechnungstext oder PDF (`app/invoice.py`, pypdf) mit Zuordnung per Artikelnummer/Name/Suche, Bestand wird eingebucht; API `/purchases/import`, `/projects/{id}/reserve`. Migration 021.
- 2026-11-04 (M42): Etikettenvorlagen je Typ (große/kleine Zeile mit Feldern, gilt für Warteschlange, XLSX, D30), Sammeldruck aller ungedruckten Etiketten einer Box samt Unterbehältern, Schnellaktionsmenü an Teilen (langer Druck, Rechtsklick, Knopf).
- 2026-11-04 (M43): Installierbare, offline-fähige App (Service Worker `/sw.js`: zuletzt gesehene Seiten offline lesbar, Buchungen ohne Netz in IndexedDB gemerkt und nachgesendet; `docs/ANDROID.md`), Home-Assistant-Sensor `/api/v1/ha` und `/api/v1/ha/item/<CODE>` (`docs/HOME_ASSISTANT.md`).
- 2026-11-04 (0.3.0): Android-App als APK (`android/`, WebView ohne Fremdbibliotheken, Kamera, Upload, Downloads, Nutzer-CA), Release-Workflow baut EXE + APK; Version 0.3.0.

## Session-Start (für autonome Umsetzung, Modell: Sonnet reicht)
> Lies CLAUDE.md und docs/STATUS.md. Setze den nächsten offenen Meilenstein um (eigener Branch), bis Tests/Lint/Typecheck grün sind. Hake ihn hier ab, pflege ARCHITECTURE/DECISIONS bei Bedarf, committe und merge nach main. Nicht zwischendurch nachfragen.

## Meilensteine
- [x] **M0 Setup**: Repo `C:\dev\sortiersystem`, uv, FastAPI-Skeleton, pytest/ruff/mypy, htmx vendored.
- [x] **M1 Datenmodell**: Behälter-Baum, Items, Protokoll (`001_init.sql`, `repo.py`).
- [x] **M2 Mobile UI**: `/c/{code}` (freier Code → Anlegen), Behälterseite mit Pfad, −/+ per htmx, Sortierkasten-Raster, Umlagern per „aufnehmen → Ziel scannen → hier ablegen“.
- [x] **M3 Suche**: FTS5 trigram + Umlaut-fähiges LIKE für Wörter < 3 Zeichen, Behälter nach Name/Code, Code im Suchfeld springt direkt.
- [x] **M4 QR-Etiketten**: `/labels` A4-Bögen (Standard 4×10 à 48,5×25,4 mm, anpassbar), Zähler „als gedruckt merken“.
- [x] **M5 Import/Export**: `/import` mit Vorschau (läuft auf DB-Kopie), Idempotenz, `slot` → Fach; `/export.json` voller Dump.
- [x] **M6 Deployment-Dateien**: ersetzt durch Docker Compose (siehe Aktuell).
- [x] **M7b Code-Schema & D30**: PRÄFIX-NNN, ART-Codes für Teile, XLSX-Export 40×12, Einstellungen.
- [x] **M7c Druckvorschau & A8**: editierbare Tabelle vor Export, A8-Bogen (A4 quer, 16 Stück).
- [x] **M7 Fotos**: Upload per Handykamera, EXIF-Drehung, 1600 px + Thumbnail, Löschen räumt Dateien auf.
- [x] **M8 Alltag**: Rückgängig + Verlauf, Favoriten, Zuletzt angesehen, PWA-Icon, Verliehen-Status, Mindestbestand/Einkaufsliste, Freie Plätze, Synonyme + Tippfehler-Suche, Schnelleingabe „3 Rollen Lötzinn“, Haiku-Prompt pro Behälter, Scan-Modus (Öffnen/Einräumen), Spracheingabe über externen Whisper (`LAGER_WHISPER_URL`), Docker + Backup-Modul.
- [x] **M9a NORB16 & Bins**: Kastenmodell, Draufsicht, Einsätze, Warteschlange, CAD-Generator.
- [x] **M9c Admin**: Einstellungen › Admin – Code-Zähler je Präfix setzen/zurücksetzen, einzelne Codes entfernen.
- [x] **M9b UX & Einstellungen**: responsives Layout, Toasts, Einstellungsregister, Backup-Knopf, HTTPS im LAN.
- [x] **M8b Spracheingabe** über KI-Gateway auf KP-DESKTOP (`http://127.0.0.1:8766`, Modell parakeet, wählbar); Diktat mit mehreren Teilen.
- [ ] **M9 Optional**: semantische Suche (lokale Embeddings), Claude-API- oder Ollama-Extraktion aus Foto+Transkript, Status „ausgeliehen“ für Werkzeug.

## Backlog 2026-10-27 (User-Wunschliste, Reihenfolge = Umsetzung)
- [x] **M10 Design Crimson Night Core**: Tokens (Nacht, Karmin, Schein …), Instrument Serif/Geist/Geist Mono, Material Symbols Rounded 300 über Rollen (`nav.home` …), alles lokal gebündelt (offline), keine Emoji. Theme konfigurierbar.
- [x] **M11 Datenmodell**: Typen als Liste mit Codes TYP-001 (mechanical, electronic, smart-home, TBD …, unterwegs neu anlegbar); Anzeigename + vollständiger Name; Modellnummer + Datenblatt (URL → PDF lokal, Such-Link); Flag „zu prüfen“ für KI-Einträge; Eingang „Zu sortieren“; Entnahmen; Projekte; API-Schlüssel.
- [x] **M12 Start & Verlauf**: „Zuletzt angesehen“ nur im Verlauf-Tab; Start = eine Eingabe für alles (Teil, Behälter, Typ), Abschnitte konfigurierbar.
- [x] **M13 Scan**: Entnehmen (Menge sofort runter, nach 7 Tagen automatisch bestätigt, am Teil stornierbar); Projekte: Teileliste per Scan systematisch einsammeln.
- [x] **M14 Etiketten**: Export immer XLSX; A4 als eigene Seite mit Auswahl aus allen etikettierten Teilen.
- [x] **M15 Lokale KI** (Gateway Chat): Teil vollständig ausfüllen ohne Haiku; „An lokale KI senden“ neben jedem Prompt-Kopieren; kompakter Prompt für lokale Modelle inkl. dynamischer Typen; alle KI-Ergebnisse mit Flag „zu prüfen“ → Tab „Freigaben“ unter Mehr (freigeben/ändern).
- [x] **M16 Sprach-Tab** in der unteren Leiste: langes Diktat + Dauer-Aufnahme Teil für Teil, getrennt durch „weiter“ oder Knopf → Einträge in „Zu sortieren“.
- [x] **M31 Netzteil-Eingang**: Feld „Eingang (Netzseite)“ (Kaltgerät C14/C8/C6, Euro-Stecker ohne Erdung, Schuko, direkt in Steckdose, Wechselaufsatz, festes Kabel, Schraubklemmen, Hutschiene, 12 V KFZ, DC, USB, PoE); Auswahl auf Start, Erkennung im Freitext/Haiku; 230 V zählt nie als Ausgangsspannung; Vollname folgt den Feldern.
- [x] **M32 Mehr Kabel-Stecker**: Auswahl auf Start um Netz (Euro-Stecker, C14/C15/C19/C20, Schuko/C13 Winkel), Drehstrom (CEE 16/32/63 A, 3p/5p, Perilex, Wieland, powerCON), Power Delivery/DC (USB-C PD, Thunderbolt, MagSafe, DC-Hohlstecker-Größen, XT30/60/90, KFZ …) und Sonstiges (RJ11, BNC, SMA, D-Sub, Speakon, MIDI …) erweitert; Synonyme im Freitext; PSU-Ausgang bekommt PD/XT60/MagSafe.
- [x] **M33 Betrieb & Material**: tägliches Backup im Hintergrund (`app/scheduler.py`, Sperrdatei, Aufbewahrung einstellbar); Mehr › Status (Backup, Speicher, KI-Gateway, Lagerwert, Haltbarkeit); Mindestbestand + Nachkaufliste mit Bedarf/Preis/Summe, „bestellt/eingetroffen“; Haltbar-bis/Geöffnet-am je Teil (Harz); Lagerwert je Behälter (inkl. Unterbehälter); Trockner mit Programmen + Verlauf (`app/dryer.py`); Slicer-Import Creality Print (G-Code/3MF, Ordner einlesen, Verbrauch von Spule abziehen, `app/slicer.py`); Foto-Erfassung mit Vision-Modell (`app/vision.py`, Start › Foto › „Mit KI auswerten“); Massenbearbeitung/-verschiebung (`/auswahl`, `app/bulk.py`); Eurobox-Maße (Dropdown Normmaße) und freies Maßfeld; Kabel/Netzteile = Einzelstücke (keine Menge, Anzahl → je Stück ein Eintrag + Etikett in der Warteschlange). Migration 017.
- [x] **M34 API/CLI/MCP live**: `GET /api/v1/schema` liefert Kategorien (Felder, Einzelstück), Arten, Tags, Aktionen; neue Endpunkte `/items/new`, `/bulk`, `/shopping`, `/value`, `/dryer`, `/print-jobs`; CLI (`schema`, `teil-neu`, `massen`, `einkauf`, `wert`, `trockner`, `drucke`) und MCP (Tool-Beschreibung `add_item` baut Kategorien beim Start aus dem Schema; Prüfung bei jedem Aufruf) folgen neuen Kategorien ohne Codeänderung. Direktdruck: siehe `docs/DIREKTDRUCK.md` (machbar, nicht umgesetzt).
- [x] **Fix Diktat**: „Stoppen und speichern“ brach auf der Sprache-Seite ab (Header-Knopf fehlt → JS-Fehler). Audio wird jetzt zuerst und allein gespeichert (Player, Audio laden), Transkription getrennt per Knopf; Prompt-Kopie/Transkript-Export wie gewohnt. Alles über API/MCP/CLI Angelegte kommt mit Tag „ki“ in die Freigaben.
- [x] **Fix Start-Kabel/Netzteil**: Kamera-Knopf startete das Mikrofon (Klasse mic), Stecker jetzt als Auswahlliste mit „Anderer …“ statt datalist (iPhone/Android), CSS/JS mit Versionsnummer gegen alten Browser-Cache.
- [x] **M30 Netzteil PSU + Eingabe je Kategorie**: Start zeigt Kategorie zuerst; bei CBL ersetzen Stecker A/B + Länge, bei PSU Volt/Ampere/Stecker das freie Feld; Netzteil-Name „Netzteil 12V 2A USB-C“, Leistung berechnet (app/psus.py).
- [x] **M29 Kabel-Felder auf Start**: bei Kategorie CBL drei Felder Stecker A, Stecker B, Länge (mit Steckervorschlägen), Freitext dann optional.
- [x] **M28 Kabel-Schema**: Profil Kabel (Stecker A, Stecker B, Länge, Standard), Name automatisch „USB-A – USB-C 2m“ (app/cables.py erkennt Kurzformen), gilt für Start, Datenblatt, Import/Haiku; Umstellung vorhandener Kabel: tools/kabel_umstellen.py.
- [x] **M27 Start-Hinzufügen**: Reihenfolge Was? → Kategorie (3×3-Matrix, Kurznamen) / Art → Wohin? → großer Knopf mit Text je Modus; Foto per Kamera-Knopf (wird jedem neuen Teil bzw. Behälter angehängt); Teil ohne Ort → Zu sortieren; Komma trennt immer ("3x1,5" bleibt ganz).
- [x] **M26 Werkzeug-Kategorie** TOL (Teile-Code TOL-001, Start-Chip, Code-Schema, Haiku-Prompt); ART nur noch für Sonstiges.
- [x] **M25 Haiku-Prompt mit DB-Kontext**: Arten (mit Präfix), Teile-Kategorien, Tags, Eigenschafts-Schlüssel und alle Behälter mit Code (eine Zeile je Behälter, max. 400); Import versteht `code: null` (neuer Code aus Art-Präfix, gleichnamiger Behälter am selben Ort wird wiederverwendet), `cat`, `tag`, `specs`.
- [x] **M24 KI-Support**: Mehr → KI-Support (Inventur Kiste für Kiste, Warteschlange ungeprüfter Teile: KI ergänzen / Passt so / Freigeben); KI füllt Eigenschaften (FIL, RES, neu CMP-Profil) nur in leere Felder, mit Plausibilitätsgrenzen; eigenes Modell für Tags & Eigenschaften (Standard fast); Restmenge per Wiegen (Spule/Flasche, m bzw. ml, unter 15 % → Einkaufsliste); Bins: oben 40×12-Code-Tag, vorne Inhaltsetikett (auch Fächer), eigene XLSX/A4.
- [x] **M23 Start & Suche**: Teil mit Kategorie-Chips (ART, FIL, RES, CNS, RAW, CBL, CMP, PPE), Behälter nur Boxen, „Alle“ mit allen Kategorien; Typ/Projekt nicht mehr auf Start (Projekte unter Mehr); Kopfzeile Lupe (klappt auf) + Verlauf + Mehr; untere Leiste Start/Einkauf/Plätze/Scannen/Sprache/Etiketten; Suche mit Tippfehler-Korrektur je Wort, Synonymen, DE/EN-Wortliste, Wortstämmen; TYP heißt jetzt TAG, in der Suche filterbar.
- [x] **M22 3D-Druck-Material**: FIL (Filament) und RES (UV-Harz) als Teile-Codes; Datenblatt mit Druck-, Trocknungs- und Mechanik-Eigenschaften; Bestell-Link + Preis (€/kg, €/l) für alle Teile; Übersicht Mehr → Filament & Harz.
- [x] **M21 Scannen**: Piepton bei erfasstem Code (Einstellung), Doppeltipp auf Einräumen = Sammelmodus (Überkategorie, dann beliebig viele Teile, neue ART-Etiketten mit Name, erst bei Bestätigen eingeräumt).
- [x] **M20 Codes-Seite** unter Mehr (Name ohne Schrägstrich + Beschreibung), Sprache DE/EN zentral unter Mehr.
- [x] **M19 Neues Code-Schema** (20 Arten in 5 Gruppen, englische Schlüssel, Namen DE/EN per Einstellung, STA→TBX, EIN→BIN, Typen immer klein).
- [x] **M18 Eigene Behälter-Arten** mit eigenem Präfix (Start „Neue Art …“, Etiketten → Code-Schema); Start-Kacheln ohne Dopplung zur unteren Leiste.
- [x] **M17 API**: REST `/api/v1` (Suchen/Lesen offen, Schreiben nur mit Schlüssel), CLI `tools/lager_cli.py`, MCP-Server `tools/lager_mcp.py`.

## Offen / zu klären
- [x] DNS `lager.home.lan` → 192.168.74.5 (AdGuard auf kp-pi3).
- [x] Firewall-Regel „KP Lager“ TCP 80/443 (Privat) vom Nutzer angelegt.

## Bekannte Probleme
- pytest-Warnung: Starlette empfiehlt `httpx2` statt `httpx` für TestClient. Harmlos; Wechsel erst nach Prüfung des Pakets.
- LXC: Debian 13 nehmen (Python 3.13); install.sh lässt uv sonst passendes Python laden.
- Raspberry Pi 2B: nur Notbetrieb, ungetestet.

## Etikettenbild + D30-Direktdruck (2026-10-30)
- `app/labelimg.py`: Etikett 320×96 px (40×12 mm), QR links, Name mittig mit Auto-Schriftgröße (einzeilig), ID groß darunter, kein Rahmen. Route `/labels/img/<CODE>.png`.
- `tools/d30_print.py`: BLE-Direktdruck (bleak, Phomemo-Protokoll, Service FF00/FF02). Verbindung getestet; Testdruck ausstehend (D30 war nicht auffindbar → einschalten, dann `uv run --with bleak python tools/d30_print.py CBL-025`).
- Direktdruck in der App: Checkbox beim Eintragen (leuchtet bei erreichbarem D30, /d30/status), Knopf am Teil solange Etikett offen, app/d30.py, LAGER_D30=1 (Standard). Bluetooth am Server-PC nötig.

## Bedienung & Direktdruck (2026-10-30)
- Druck: COM-Port (Bluetooth-Seriell, Auto-Erkennung, `LAGER_D30_PORT`/`LAGER_D30_ADDR`) zuerst, bei Fehler BLE. Vorschau: „Auf D30 drucken“ + „In Warteschlange“ (`/labels/export` fmt=d30|queue).
- Untere Leiste ohne „Plätze“ (bleibt in Mehr/Seitenleiste). Hinzufügen: 3×3-Matrix (seitlich scrollbar) für Kategorien und Behälterarten, zuletzt verwendete vorn (Cookies qa_cats/qa_kinds).
- Filament/Harz: Auswahllisten (app/choices.py; Standard + im Lager Vorhandenes, häufigste zuerst), Name = Hersteller Werkstoff Farbe, Anzahl = Menge. Neues Feld „Hersteller“.
- Behälter: Größe aus vorhandenen Boxen/Euro-Normen, Luftdicht (Migration 018). Neue Arten Maschine (MAS) und Filamenttrockner (TRO) bekommen sofort Code + Etikett in der Warteschlange.
- Trockner-Scan: Trockner-Etikett scannen → 10 min Modus (Cookie), dann Filament-Etikett(en) = getrocknet mit Datum/Uhrzeit (dry_log, Seite /trockner/scan/<id>).
- Inhalt unter „Wohin?“ (/n/<id>/inhalt) und Behälterliste: ab dem 10. Eintrag „Mehr anzeigen“.
- Fix: ausgeblendete Kategorie-Felder werden nicht mehr mitgeschickt (Anzahl ging verloren).

## Katalog, Einsatz-Assistent, Baum (2026-11-03)
- `/neu` (Nav „Anlegen“, Tab „Katalog“ im Hinzufügen-Formular): ~55 Teile-Typen in 8 Gruppen (app/catalog.py) aus den Sortierkasten-Fotos + Heimwerken/3D-Druck/Laser/Elektronik. Felder als Chips + Datalist, Live-Namensvorschau, danach gleicher Typ mit leeren Feldern (Ziel bleibt). Elektronik bekommt das Datenblatt-Profil „Elektronikbauteil“.
- `/neu/bin`: Einsatz-Assistent (Kasten, freie Zelle, X×Y, Fächeranzahl, je Fach Art+Variante+Menge, Etiketten). 
- Übersicht: Baum mit lazy Zweigen (`/n/<id>/zweig`, `/baum`), auf der Startseite statt Raumkarten; ab 10. Eintrag „Mehr anzeigen“.

## GitHub-Repository (2026-11-03)
- Projekt als privates GitHub-Repository bereitgestellt (README, docs/DEVELOPMENT.md, CI in `.github/workflows/ci.yml`). Weiterarbeit in der Cloud: `docs/DEVELOPMENT.md` lesen, dann hier die offenen Punkte abarbeiten.
- Katalog: Typ-Liste mit einklappbaren Gruppen, Scrollposition bleibt beim Wechsel erhalten.

## Offene Punkte (Stand 2026-11-03)
- Handy-Test (CA, Bedienung Katalog/Baum), D30: Papier-Test des neuen Etikettenlayouts über die App, Bin-Testdruck, echter Creality-Print-Export, Vision-Test.
- Autostart (geplanter Task) nur mit ausdrücklichem OK; Umzug auf Pi (Docker) vorbereitet, ungetestet.
- Ideen: Maschinen-Wartung, Inventur-Scan, Etikett nachdrucken, Letzten Eintrag kopieren, Harz-Ablaufwarnung, Backup auf zweites Medium.
