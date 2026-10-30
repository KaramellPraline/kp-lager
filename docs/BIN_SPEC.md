# Bin-Spezifikation (Kistenberg NORB16) – für einen anderen parametrischen Generator

Quelle: deine Vorgaben (2026-10-26/27), Vermessung deiner STEP-Bins und der Original-STL
(`norp-16-bins`), Umsetzung in `cad/norb_bins.py` (build123d). Maschinenlesbar: `cad/bin_params.json`.
Koordinaten: X = Breite (parallel zu den Bodenrippen), Y = Tiefe (kreuzt die Rippen, + = Rückwand,
− = Vorderseite/Greifseite), Z = Höhe (0 = Boden außen). Alle Maße in mm.

## 1. Deine Vorgaben (wörtlich sinngemäß)
1. Standard-Einsätze: **1x1, 1x2, 2x2**, früher mit **Unterteilungen** erzeugt.
2. **Alle Bins, die nicht nur in der Breite angepasst sind, brauchen Rillen**, um in die Box zu passen.
3. Ein **dedizierter Ort für ein 40 × 12 mm Etikett**.
4. Innen **Rundungen**; an der **Vorderseite eine 15 mm Rundung**, damit Kleinteile besser herauskommen.
5. Die **Rille bei Bedarf runden**, damit der Druck **ohne Support** sicherer wird.
6. Etiketten-Konzept: oben auf dem Bin ein **fester 40×12-QR-Tag** (Code = Kasten + Position, bleibt
   gleich); der **Inhalt** kommt auf ein **separates Inhaltsetikett** (ohne QR, vorne/außen).

## 2. Raster und Außenmaß
| Parameter | Wert | Hinweis |
|---|---|---|
| Rastermaß (pitch) | **54,77** | Außenmaß = N × 54,77 (Breite w, Tiefe d) |
| Höhe | **45,5** fest | Box-Innenhöhe; eigene STEP-Bins waren 45,35 |
| Breite X / Tiefe Y | w × 54,77 / d × 54,77 | w, d ≥ 1 |
| Außenecken (senkrecht) | R 3,0 | |
| Formschräge | 2,3 je Seite (unten enger als oben) | Original ≈ 2,2 |
| Fase Unterkante | 3,0 | |
| Wand / Boden / Trennwand | 1,2 / 1,2 / 1,2 | |
| Trennwand-Oberkante | 2,0 unter Oberkante | |

Box (Kistenberg NORB16): außen 399 × 303 × 50, Raster **5 Spalten × 7 Zeilen** (A1 oben links,
Zeile = Buchstabe, Spalte = Zahl), Griff blockiert **C1, D1, E1**. Bin-Größe „BxT“ = Spalten × Zeilen.
Standard-Auswahl in der App: 1x1, 2x1, 1x2, 2x2, 3x1, 4x1; Unterteilungen 1x1, 2x1, 3x1, 4x1, 5x1, 1x2, 2x2, 3x2.
Generator-Standardsatz (12): 1x1; 1x1 div 2x1; 1x1 div 3x1; 2x1; 2x1 div 3x1; 2x1 div 5x1; 1x2;
1x2 div 1x2; 1x2 div 3x1; 2x2; 2x2 div 2x1; 2x2 div 3x2.

## 3. Unterteilung (Fächer)
- `div_x` Fächer nebeneinander (Trennwände quer zu X), `div_y` hintereinander (quer zu Y).
- Gleichmäßig verteilt: Wand i bei x = −Breite/2 + i·Breite/div_x; analog Y.
- Trennwand 1,2 dick, reicht bis 2,0 unter die Oberkante.

## 4. Rillen (Bodenrippen der Box)
- Rippen laufen in **X**-Richtung. Bins mit Tiefe d = 1 (nur breiter) brauchen **keine** Rille;
  bei d > 1 an **jeder inneren Rastergrenze** y = −Tiefe/2 + k·54,77 (k = 1 … d−1) eine Rille quer über die ganze Breite.
- Rillenprofil (Querschnitt, Y–Z): Breite unten **9,8**, oben **5,0**, Höhe der Flanken **4,6**,
  darüber **45°-Spitzbogen** (Spitze bei Höhe 4,6 + 2,5) statt flacher Brücke → ohne Support druckbar.
- Gehäuse um die Rille: Wand 1,2 rundum, Boden +1,2 (Rille bleibt dicht, Hohlraum bleibt frei).

## 5. Innenform
- Senkrechte Innenecken **R 5,0**.
- Übergang Boden → Wand innen **R 2,5** (keine Kanten, Kleinteile sammeln sich nicht).
- **Greifmulde vorn R 15** (Viertelkreis zwischen Boden und Vorderwand) **je Fachreihe**
  (also auch vor jeder inneren Reihentrennwand); bei flachen Reihen max. 50 % der Reihentiefe. 0 = aus.

## 6. Etikettenablage (40 × 12)
- Etikett 40,0 × 12,0; Spiel 0,3 rundum → Mulde **40,6 × 12,6**, Tiefe **0,6**.
- Ablage an der **Rückwand (+Y)**: Tiefe (Y) **15,0**, Dicke **2,0**, Oberkante 0,4 unter Bin-Oberkante;
  unten **45°-Stütze** (Support-frei). Mulde mittig auf der Ablage.
- Mindestbreite: Innenbreite ≥ 42 (sonst „zu schmal“).
- Optional abschaltbar (`label = false`).

## 7. Drucklogik
- Alles ohne Support: Spitzbogen-Rille, 45°-Etikettenstütze, gerundeter Boden.
- Ausgabe STEP + STL, Dateiname `Bin_{w}x{d}[_div{dx}x{dy}][_label]`.

## 8. Annahmen / noch zu prüfen
- Rippenrichtung und Griffzellen stammen aus Fotos → vor Serien **einen Testbin** drucken (Passung, Rippenrichtung).
- Mittlere Toleranzen (Wand 1,2, Spiel Etikett 0,3) sind Vorgaben aus den Originalen, nicht am Drucker verifiziert.
