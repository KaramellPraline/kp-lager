# Kistenberg NORB16 & Bin-Generator

## Box
- Außen 399 × 303 × 50 mm, Raster **5 Spalten × 7 Zeilen** (A1 oben links), Griff blockiert **C1, D1, E1**.
- Bodenrippen laufen **waagerecht** (entlang der Spalten-Richtung) zwischen den Zeilen
  → Bins, die nur breiter werden (Bx1), brauchen keine Rille; Tiefe > 1 kreuzt Rippen → Rille.
- Annahmen aus Fotos (Rippenrichtung, Griffzellen) – vor dem Druck großer Serien 1 Testbin prüfen.

## Vermessung (2026-10-26)
| Quelle | Befund |
|---|---|
| Eigene STEP-Bins (KistenbergNORS) | Außenmaß = N × 54,77 mm, Höhe 45,35 (Ziel 45,5), keine Rillen |
| Original-STL (norp-16-bins) | Höhe 45,5, Wand 1,2, Formschräge ~2,2 mm/Seite, Fase 3 mm, Rille unten 9,8 mm → oben ~5 mm, ~4,6 mm hoch |

## Generator `cad/norb_bins.py` (build123d)
```bash
uv run --group cad python cad/norb_bins.py 2x1 --div 3x1      # Breite x Tiefe, Fächer
uv run --group cad python cad/norb_bins.py 1x2 --no-label
uv run --group cad python cad/norb_bins.py --standard         # 12 Standard-Einsätze
```
- Ausgabe `out/bins/*.step` + `*.stl` (gitignored), ~0,5 s pro Bin.
- Etikettenablage 40×12 mm (Mulde 40,6×12,6×0,6) an der Rückwand (+Y), 45°-Stütze → ohne Support druckbar.
- Alle Maße sind Felder von `BinSpec` (Raster, Wand, Rille, Ablage …); Höhe fest `HEIGHT = 45.5`.
- Tests: `uv run --group cad pytest tests/test_cad.py` (ohne `cad`-Gruppe übersprungen).
