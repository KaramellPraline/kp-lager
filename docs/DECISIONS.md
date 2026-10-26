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
| 2026-10-26 | Etiketten-Codes 4-stellig fortlaufend, Druck-Zähler in `meta` | Kurz, gut lesbar; nie doppelt gedruckt. |
| 2026-10-26 | Hostname-Empfehlung `lager.fritz.box` bzw. `lager.home.arpa` statt `lager.home` | `.home.arpa` ist der reservierte Heimnetz-Suffix; Fritz!Box löst Hostnamen automatisch auf. |
