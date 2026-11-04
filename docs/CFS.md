# CFS-NFC-Platte für Filament (seit 1.5.0)

Statt eines normalen Etiketts bekommt eine Filamentspule eine **3D-gedruckte Platte** mit NFC-Tag
(Creality CFS liest MIFARE Classic 1K), **Klebelasche** und aufgeklebtem Etikett.

## Ablauf
1. Filament öffnen → Karte **CFS-NFC-Platte** → „Platte & Tag vorbereiten“ (`/items/<id>/cfs`).
2. Modell drucken: `app/static/cad/cfs-platte.stl|step` (Rückseite aufs Bett, 0,2 mm, PLA/PETG).
3. Leeren **MIFARE-Classic-1K-Coin-Tag Ø 25 mm** in die Rückseiten-Tasche legen.
4. **Werte kopieren & SpoolID öffnen**: Die KP-Lager-Android-App kopiert die Werte und startet
   [SpoolID](https://play.google.com/store/apps/details?id=dngsoftware.spoolid) („Cfs RFID“); dort eintragen und den
   Tag beschreiben. Im Browser nur „kopieren“.
5. Etikett (12 × 40, D30) in die Mulde, Klebelasche auf die Spulenflanke.

SpoolID hat keine Schnittstelle zur Datenübergabe (kein Intent/Deep-Link); darum geht der Weg über die Zwischenablage.
Das Lager schreibt selbst keine Tags und enthält keine CFS-Schlüssel.

## Werte
Aus dem Filament-Datenblatt: Hersteller, Werkstoff, Farbe (neues Feld **Farbe (Hex)**, sonst aus Farbwörtern wie
„Weiß“), Gewicht, Länge (≈ aus Gewicht, Durchmesser, Dichte; Standard 1,75 mm / 1,24 g/cm³), Seriennummer (Ziffern des
FIL-Codes). API: `GET /items/<id>/cfs.json`. Code: `app/cfs.py`.

## Modell (`cad/cfs_tag.py`)
Platte 46 × 42 × 2,4 mm, Rückseite Tag-Tasche Ø 25,4 × 1,3 mm, Vorderseite Etikettenmulde 40 × 12 × 0,4 mm,
Klebelasche 20 × 30 × 0,8 mm bündig mit der Rückseite. Anpassen:
`uv run --group cad python cad/cfs_tag.py --coin 25.4 --tab 20 --out out/cfs`
(danach die Dateien nach `app/static/cad/` kopieren, wenn sie der Standard werden sollen).

## Android
`MainActivity` stellt `window.KPLager.openSpoolId(text)` bereit (Zwischenablage + SpoolID starten, sonst Play Store);
`<queries>` im Manifest erlaubt die Paketabfrage. Die APK entsteht mit dem Release (`docs/RELEASE.md`).
Offen/ungeprüft: Format der Tags und Passung des Modells am echten CFS (Maße nach Messung anpassen).
