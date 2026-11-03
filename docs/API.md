# API für externe Werkzeuge und KI (Stand 2026-11-03)

Basis: `https://<host>/api/v1` · interaktive Beschreibung aller Endpunkte: `https://<host>/docs`.

## Schlüssel
Einstellungen › Admin › API-Schlüssel. Zwei Rechte:

| Recht | darf |
|---|---|
| **Lesen** | alles abfragen (Suche, Baum, Projekte, Einkaufsliste …) |
| **Lesen und schreiben** | zusätzlich Teile/Behälter anlegen und ändern, entnehmen, umlagern, Projekte, Einkäufe, Karten, Inventur |

Header `X-API-Key: kpl_…` (oder `Authorization: Bearer kpl_…`). Der Klartext wird nur einmal angezeigt.
Standard: Lesen ist im LAN offen. Einstellungen › Betrieb › „API: auch Lesen nur mit Schlüssel“ verlangt
auch zum Lesen einen Schlüssel (empfohlen, sobald das Lager von außen erreichbar ist).

## Lesen
`GET /overview` · `/tree?depth=` · `/items?container=&low=&limit=&offset=` · `/items/{ref}` · `/containers/{ref}` ·
`/search?q=` · `/schema` · `/shopping` · `/value` · `/projects` · `/projects/{id}` · `/suppliers` · `/inventory/due`

`{ref}` ist ein Code (`ART-0007`, `EUR-003`) oder die numerische ID.

## Schreiben (Schlüssel mit Schreibrecht)
| Aufruf | Zweck |
|---|---|
| `POST /items` · `POST /items/new` | Teile anlegen (Schnelleingabe / mit Kategorie und Eigenschaften) |
| `PATCH /items/{ref}` | name, notes, price, min_qty, order_qty, on_list, archived, `qty` (absolut) oder `qty_delta` |
| `DELETE /items/{ref}?hard=` | archivieren (Standard) oder endgültig löschen |
| `POST /items/{ref}/take` · `/move` | entnehmen (7 Tage stornierbar) · umlagern |
| `POST /containers` · `PATCH /containers/{ref}` | Behälter anlegen, umbenennen, umlagern |
| `POST /projects` · `/projects/{id}/lines` · `/projects/{id}/shopping` | Projekt mit Stückliste planen, Fehlmengen auf die Einkaufsliste |
| `POST /items/{ref}/purchases` | Einkauf (Lieferant, Menge, Stückpreis) erfassen |
| `POST /items/{ref}/cards` · `/containers/{ref}/cards` | Notiz- oder Pinout-Karte |
| `POST /inventory/items/{ref}` · `/inventory/containers/{ref}/done` | Inventur bestätigen / abschließen |
| `POST /bulk` · `/import` · `/dryer/start` | Massenänderung, JSON-Import, Trockner |

## Beispiel: Projekt planen lassen
1. `GET /overview`, `GET /tree`, `GET /items?limit=500` – Bestand lesen.
2. `POST /projects` mit `{"name": "Wetterstation", "lines": [{"item": "ART-0007", "qty": 5}, {"name": "BME280", "qty": 1}]}`
   – die Antwort zeigt je Zeile `ok` / `teil` / `fehlt`, Fehlmengen und Kosten.
3. `POST /projects/{id}/shopping` – Fehlendes landet auf der Einkaufsliste.

## Typen, Einkauf, Home Assistant
`GET /types/catalog` (alle Typen mit Feldern) · `GET /types/catalog/{key}/items` · `PATCH /items/{ref}` mit `ctype`, `fields`, `rename` ·
`POST /purchases/import/preview` und `/purchases/import` (Rechnung/CSV) · `POST /projects/{id}/reserve?release=` ·
`GET /ha` und `/ha/item/{ref}` für Home Assistant (siehe `docs/HOME_ASSISTANT.md`).

## MCP-Server
`uv run --group mcp python tools/lager_mcp.py` (Vorlage `docs/mcp.example.json`) bietet dieselben Funktionen als
Werkzeuge für KI-Assistenten (`LAGER_URL`, `LAGER_API_KEY`). Mit Lese-Schlüssel funktionieren alle Abfragen;
Schreibwerkzeuge melden dann „403: Dieser Schlüssel darf nur lesen“.
