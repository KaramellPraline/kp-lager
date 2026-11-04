# Entscheidungen

| Datum | Entscheidung | Warum |
|---|---|---|
| 2026-10-26 | Eigene schlanke App statt Homebox/InvenTree | Kern-UX (Scan → Einlagern/Entnehmen/Sprechen) ist der ganze Zweck; mit Homebox wären es zwei Oberflächen. |
| 2026-10-26 | FastAPI + SQLite (ohne ORM) + Jinja2/HTMX, kein JS-Build | Wenige Dateien, wenig Tokens, Python passt zu Whisper/Embeddings, eine Datei = einfaches Backup. |
| 2026-10-26 | Suche ohne LLM: FTS5 trigram, später lokale Embeddings | Schnell, offline, kostenlos; trigram löst deutsche Komposita. Ein „Such-Agent“ bringt dafür kaum Mehrwert. |
| 2026-10-26 | Erst-Inventur per Haiku im Chat (keine API), Import als JSON | Nutzerwunsch: erst manuell funktionsfähig; keine Kosten/Keys, App bleibt KI-frei. |
| 2026-10-26 | Erfassung pro Behälter grob (Liste + optionale Mengen), nicht jede Schraube | Sonst bricht die Inventur ab; genaue Mengen nur wo nötig. |
| 2026-10-26 | Ein QR pro Behälter, Fächer von Sortierkästen per Raster (A1…) | Weniger Etiketten, Fächer ändern sich selten. |
| 2026-10-26 | Codes vorab auf Bögen drucken, unbekannter Code → Anlegen | Neue Behälter nebenbei erfassen, keine Druckerei pro Box. |
| 2026-10-26 | Betrieb: Debian-LXC auf Proxmox (Ryzen 5 5600), systemd, kein Docker | Weniger Overhead als Docker-in-LXC; Backup per vzdump + SQLite-Dump. |
| 2026-10-26 | Pi 2B nur als Notfall-Ersatz für den Kern, nicht Zielplattform | ARMv7, 1 GB RAM: Whisper/Embeddings dort nicht sinnvoll. |
| 2026-10-26 | HTTPS via Caddy `tls internal`, Root-CA aufs Handy | Browser erlauben Kamera/Mikrofon nur in sicherem Kontext. |
| 2026-10-26 | Whisper (faster-whisper small, CPU) nachrangig als separater Dienst | KI hat niedrige Priorität; Kern darf nicht davon abhängen. |
| 2026-10-26 | Code-Repo außerhalb Google Drive (`C:\dev\sortiersystem`) | Drive-Sync beschädigt SQLite/.git/venv; in Drive nur Backups. |
| 2026-10-26 | Speicherstruktur = Baum aus Behältern (`parent_id`), Items an genau einem Knoten | Raum/Regal/Ebene/Stapel/Box/Fach einheitlich; Umzug = ein Feld; Pfad per rekursivem CTE. |
| 2026-10-26 | Interne `id` + optionaler `code` statt Code als PK | Nicht jeder Knoten braucht ein Etikett (Raum, Ebene, Fach); Etikett nachträglich zuordenbar. |
| 2026-10-26 | Sortierkasten-Fächer als Kind-Behälter (aus `grid` erzeugt) statt `slot`-Feld am Item | Einheitliche Suche/Pfade; Einsätze können umziehen. |
| 2026-10-26 | Kein Artikelstamm: gleiches Ding an zwei Orten = zwei Items | Heim-Lager braucht keine Stammdaten; Suche gruppiert nach Namen. Bei Bedarf später Tabelle `article`. |
| 2026-10-26 | Mengen nie < 0, ungezählte Items (qty NULL) protokollieren nur | Verhindert Datenmüll, ohne Zählzwang. |
| 2026-10-26 | Umlagern per „aufnehmen → Ziel scannen → hier ablegen“ (Cookie) statt Auswahlliste | Passt zum Scan-Ablauf mit der normalen Kamera-App, kein QR-Scanner im Browser nötig. |
| 2026-10-26 | Import-Vorschau läuft auf In-Memory-Kopie der DB | Gleicher Code für Vorschau und Übernahme; echte DB bleibt bei Fehlern unberührt. |
| 2026-10-26 | Code-Schema PRÄFIX-NNN (RAU/REG/STA/EUR/KIS/SOR 3-stellig, ART 4-stellig), Zähler je Präfix | User-Entscheidung; Code = Identität, nie Ort. Ersetzt rein numerische Codes. |
| 2026-10-26 | Fächer ohne eigenes Etikett; Teile im Fach bekommen ART-Etikett (QR + Name) | User-Entscheidung; Scan führt direkt zum Teil. |
| 2026-10-26 | ART-Code automatisch für neue Teile, per Einstellung abschaltbar (Standard an), plus Knopf am Teil | User-Entscheidung. |
| 2026-10-26 | QR-Inhalt in Großbuchstaben (`HTTP://HOST/C/CODE`) | Alphanumerik-Modus → QR eine Version kleiner, auf 40×12 mm (D30, 203 dpi) besser scannbar. |
| 2026-10-26 | D30-Druck über XLSX-Export (Code, QR, Text, Zusatz); Download zählt als gedruckt | D30-App kann Excel-Batch; kein Treiber/Direktdruck nötig. |
| 2026-10-26 | Hostname `lager.home.lan` (User-Entscheidung) | Steht in jedem QR-Code; DNS-Eintrag im Router nötig. |
| 2026-10-26 | App-Name „KP Lager“, zentral als `APP_NAME` in `app/web.py` | Ein Ort für Titel, Kopfzeile, Etiketten, Homescreen-Name. |
| 2026-10-26 | Etikettendruck immer über Vorschau-Tabelle mit editierbarem Text; Namen nur auf Wunsch ins Lager übernehmen | User-Wunsch; Etikettentext oft kürzer als der volle Name. |
| 2026-10-26 | A8-Etiketten (A4 quer, 4×4, dünne Schnittlinien, QR links, Name, Code) ersetzen den A4-Bogen 48,5×25,4 | User-Vorgabe; groß genug für Euroboxen, kein Spezialpapier nötig. |
| 2026-10-26 | Vorrats-Codes erst beim Export reservieren | Abgebrochene Vorschau verbraucht keine Nummern. |
| 2026-10-26 | QR-Basis-URL Standard `https://lager.home.lan` | User-Wunsch; DNS-Eintrag in AdGuard nötig. |
| 2026-10-26 | Hosting per Docker Compose (App + Caddy) statt systemd-LXC; kp-pi3 verworfen | User-Entscheidung; portabel auf jeden Docker-Host. LXC-Skripte entfernt. |
| 2026-10-26 | Whisper nicht im App-Container, sondern externer OpenAI-kompatibler Dienst (`LAGER_WHISPER_URL`) | Schwache Hosts überfordert; Mikrofon-Knopf nur sichtbar, wenn konfiguriert. |
| 2026-10-26 | Scan im Browser: BarcodeDetector, Fallback jsQR (vendored) | iOS Safari hat keinen BarcodeDetector; keine CDNs im LAN. |
| 2026-10-26 | Zuletzt angesehen per Cookie (pro Gerät), Favoriten in der DB (für alle) | Verlauf ist persönlich, Favoriten geteilt. |
| 2026-10-26 | Rückgängig für Entnehmen/Einlagern/Umlagern/Hinzufügen über Event-Log (`prev_container_id`, `undone`) | Fehlbedienung am Handy schnell korrigierbar; Löschen bleibt mit Bestätigung. |
| 2026-10-26 | Bin-Generator mit build123d (statt CadQuery), eigene Abhängigkeitsgruppe `cad` | User hatte build123d; App-Image bleibt schlank. |
| 2026-10-26 | Raster 54,77 mm, Höhe fest 45,5, Rillen nur bei Tiefe > 1 (Rippen laufen in Breitenrichtung) | Vermessung eigener STEP- und Original-STL-Bins; User-Aussage zu Rillen. |
| 2026-10-26 | Rille mit 45°-Spitzbogen, Greifmulde R15 vorn, Innenecken R5 | User-Wunsch; support-frei druckbar. |
| 2026-10-26 | Einsätze als Behälterart `einsatz` (EIN-Codes) mit Größe BxT in einem Kasten-Modell | Bins tragen das Etikett (40×12-Ablage); Fächer bleiben Kind-Behälter. |
| 2026-10-26 | Etiketten-Warteschlange (`label_queue`), gleicher Code = Text aktualisieren | Batch-Druck; Bin-Etikett folgt dem Inhalt. |
| 2026-10-26 | HTTPS im LAN per eigener CA (`tools/devcert.py`) direkt in uvicorn statt Caddy unter Windows | Keine Fremd-Binärdateien; Docker-Variante nutzt weiter Caddy. |
| 2026-10-26 | Einstellungen als Register (`app/prefs.py`) statt Einzel-Routen | Neue Optionen = eine Zeile, Seite generiert sich. |
| 2026-10-26 | Layout: Handy untere Navigation + Scan-Knopf, ab 900 px Seitenleiste + 2 Spalten | Daumenbedienung; Desktop nutzt Breite. |
| 2026-10-26 | Spracheingabe über eigenes KI-Gateway (OpenAI-kompatibel), auf demselben PC via localhost ohne Token; Standardmodell parakeet | Test: parakeet erkannte „Lötzinn“ korrekt und schneller als whisper-1; kein Secret nötig. Token per `LAGER_WHISPER_TOKEN` für andere Hosts. |
| 2026-10-26 | Diktat mit „und“/Komma vor einer Zahl wird in mehrere Teile getrennt | Natürliche Spracheingabe „3 Rollen Lötzinn und 50 M3 Muttern“. |
| 2026-10-26 | Spracheingabe jetzt über Gateway-Port 8766 (`http://127.0.0.1:8766`) | User: Whisper-Gateway umgezogen; 127.0.0.1 statt localhost (eindeutig IPv4, kein Token). |
| 2026-10-26 | Admin-Tab: Zähler je Präfix setzen/zurücksetzen, Codes einzeln von Objekten lösen; nie unter höchste vergebene Nummer | Fehler korrigierbar, ohne doppelte Codes zu riskieren. |
| 2026-10-27 | Design: Crimson Night Core (Artifact JHToaeZoynmKmu53rCfFU4), Icons nur über Rollen, Fonts lokal gebündelt | User-Vorgabe; App läuft offline im LAN. |
| 2026-10-27 | Datenblatt: PDF wird von einer eingetragenen/KI-vorgeschlagenen URL automatisch lokal gespeichert, plus Such-Link | Keine kostenlose Datenblatt-API ohne neues Konto. |
| 2026-10-27 | Entnahme: gezählte Teile sofort −Menge, Storno stellt her, Bestätigung nach 7 Tagen automatisch; ungezählte → „entnommen“, nach 7 Tagen archiviert (nicht gelöscht) | Fehlerfrei rückgängig machbar, nichts geht verloren. |
| 2026-10-27 | Lokale KI über Gateway 8766 (`LAGER_AI_URL`, Standard = Whisper-URL), Modell `mid` wählbar; kompakter Prompt mit dynamischen Typen | Getestet: Diktat mit 2 Behältern → 6 Teile in ~15–28 s, Zahlwörter → Mengen, Modellnummern erkannt. |
| 2026-10-27 | KI-Ergebnisse immer mit Flag „zu prüfen“; Vervollständigen sichert alten Stand (`item.ai_backup`) für Ablehnen | Keine stillen KI-Änderungen am Bestand. |
| 2026-10-27 | API v1: Lesen/Suchen ohne Schlüssel (nur LAN), Schreiben nur mit `kpl_`-Schlüssel (Header `X-API-Key`/Bearer); CLI und MCP sprechen nur die REST-API | Ein Zugriffsweg, Rechte zentral; MCP SDK auf v1 gepinnt (FastMCP, v2 hat API umbenannt). |
| 2026-10-27 | Eigene Behälter-Arten in `container_kind` mit 3-Buchstaben-Präfix; CHECK auf `container.kind` entfällt (Migration 010) | Nutzer will Arten unterwegs ergänzen; Prüfung liegt jetzt in `app/kinds.py`. |
| 2026-10-27 | Code-Schema nach Nutzerliste (WBA, WAL, DRW, TBX, MCF, MOD, BOX, BIN, CNS, RAW, CBL, CMP, PPE …); Arten-Schlüssel englisch, Anzeige DE/EN wählbar; alte deutsche Schlüssel als Alias beim Import; Typen immer kleingeschrieben | User-Vorgabe; Alias hält alte Haiku-JSONs lauffähig. |
| 2026-10-27 | FIL/RES sind Teile-Präfixe (wie ART, 3-stellig), Eigenschaften als JSON `item.specs` mit fester Feldliste je Material | Spule/Flasche ist ein Teil mit Menge; JSON hält das Schema flexibel ohne viele Spalten. |
| 2026-10-27 | CNS/RAW/CBL/CMP/PPE sind Teile-Kategorien (Code-Präfix am Teil), keine Behälter-Arten; TYP heißt TAG (alte TYP-Codes werden umgeleitet) | Nutzer wählt sie beim Teil-Hinzufügen; Verbrauch/Material sind Dinge, keine Orte. |
| 2026-10-27 | KI-Eigenschaften: Modell fast als Standard (3–7 s/Teil, mid 25–40 s), nur leere Felder, Zahlen mit Plausibilitätsgrenzen, Richtwerte im Prompt; alles bleibt „zu prüfen“ | Live-Test: fast ohne Grenzen riet grob falsch (PETG 180 °C, Fluss 150 mm³/s). |
| 2026-10-27 | Bin-Etiketten getrennt: oben fester 40×12-QR-Tag (Kasten + Position), vorne Inhaltsetikett ohne QR (Warteschlange content_queue) | Inhalt ändert sich, der Code-Tag nicht. |

- 2026-10-29 Kabel (CBL) und Netzteile (PSU) sind Einzelstücke: keine Menge, jedes Stück ein Eintrag mit eigenem Code/Etikett (Meterware mit Einheit m bleibt zählbar). Warum: jedes Stück wird einzeln beschriftet und gefunden.
- 2026-10-29 CLI/MCP lesen Kategorien aus `/api/v1/schema` statt sie fest zu kodieren. Warum: neue Kategorien/Felder erscheinen ohne Änderung an tools/.
- 2026-10-29 Backup läuft im Server-Prozess (Thread, Sperrdatei) statt als Windows-Aufgabe. Warum: kein Autostart/Admin nötig, beide Prozesse (80/443) sichern nur einmal.

- 2026-10-30: D30-Direktdruck über Bluetooth-Seriell (COM) zuerst, BLE als Rückfall; USB des D30 ist nur Ladeanschluss (kein Datenweg gefunden). Trockner-Ablauf per Cookie (je Gerät/Handy), nicht serverweit.
| 2026-11-03 | Alle KI-Bausteine entfernt (Whisper/Diktat, lokale KI, Foto-Erkennung, KI-Support, Freigaben, Haiku-Prompt); API markiert nichts mehr als „KI“ | Nutzerwunsch: System ohne KI, mehr Benutzerfreundlichkeit. Alte Spalten (`review`, `ai_backup`) und Tabelle `note` bleiben unberührt (Daten bleiben erhalten). |
| 2026-11-03 | Start `/` = reiner Bestandsbrowser; Anlegen nur im Tab „Hinzufügen“ (`/neu`) mit Reitern Teile · Behälter · Kabel & Material · Einsatz | Ein Ort zum Anlegen; Behälter wie Teile nach dem Katalog-Prinzip (Art links, Felder rechts, Etikett-Option, bleibt für den nächsten offen). |

- 2026-11-04 (1.0.0/1.1.0): Standard-Etikett dreizeilig (Typ+Spec · Maße · Code); Vorrang gespeichertes Layout > Haupt-/Zusatzzeile > Standard. Warum: einheitlich lesbar ohne Handarbeit je Typ.
- 2026-11-04: **XLSX-Export entfernt** (D30 druckt direkt per Agent/BLE; `openpyxl` aus den Abhängigkeiten). Warum: nicht mehr gebraucht, ein Weg weniger.
- 2026-11-04: **A4 nie automatisch**: immer Warteschlange `a4_job`, Anordnung per Regalpackung, Druck als PDF per IPP erst nach Bestätigung. Warum: Farbdrucker/Papierkosten, Kontrolle vor dem Druck.
- 2026-11-04: A4-Typen `tag`, `bin_side`, `box` (abgerundeter Rahmen, Länge×Breite), `content`; Rot erlaubt. Warum: Seitenetiketten für Bins mit allen Fächern, Boxen mit Maßen.
- 2026-11-04: Filament/Harz-Klassen als Presets (`preset`), manuell eingetragene Hersteller werden gemerkt; Werkstoff = Kunststoff + Zusatz mit Prozent. Warum: schnelles Anlegen von Spulen.
- 2026-11-04: Dezimalzahlen systemweit mit Punkt (Komma→Punkt beim Tippen und serverseitig). Warum: Nutzerwunsch, einheitliche Daten.
- 2026-11-04: Bin-Parameter in einer Datei `bins.json` (`kp-lager-bins/1`) für `cad/norb_bins.py --file`; Einsätze per Drag & Drop verschieben. Warum: parametrischer Druckgenerator braucht alle Einstellungen an einem Ort.
- 2026-11-04 (1.2.0): Gescheiterter Druck legt Etiketten automatisch in die Warteschlange. Warum: nichts geht verloren, wenn der Agent offline ist.
- 2026-11-04: Filament/Harz sind Einzelstücke (`Type.single`); Kunststoffanteil = 100 − Zusatz. Warum: jede Spule eigener Code/Restgewicht; weniger Eingabe.
- 2026-11-04: API-Schreibschlüssel per Einstellung abschaltbar (`api_write_key`, Standard an). Warum: Debuggen von CLI/MCP ohne Schlüsselverwaltung.
- 2026-11-04 (1.3.0): Schrift Roboto wird mitgeliefert. Warum: das Docker-Image hat keine Systemschriften, Pillow-Standardschrift kennt keine Umlaute/ß.
- 2026-11-04: A4-Etiketten sind frei gestaltbar (Typ `layout`: Zeilen mit Farbe, QR, Rahmen) und übernehmen Name/Code aus dem Behälter. Warum: gleiche Konfigurierbarkeit wie das kleine Etikett.
- 2026-11-04 (1.4.0): Einsätze können lose (ohne Sortierkasten) angelegt werden und werden später im Kasten eingesetzt. Warum: Einsätze entstehen oft vor dem Kasten bzw. werden getauscht; Rastermaß (size) und Teilung (grid) sind die gleichen Felder wie bei im Kasten angelegten Einsätzen.
- 2026-11-04: Scanner erkennt nur das sichtbare Quadrat und fokussiert per Tippen. Warum: schneller, weniger Fehlscans am Bildrand; Fokuspunkt ist die einzige Hilfe bei Nahaufnahmen kleiner Etiketten.
- 2026-11-04 (1.5.0): CFS-Tags werden nicht vom Lager geschrieben, sondern über die App SpoolID (Zwischenablage-Übergabe, kein Intent-API). Warum: Format/Schlüssel sind Community-Reverse-Engineering, SpoolID ist gepflegt; weniger eigener Krypto-Code. Normales Etikett bleibt Standard.
