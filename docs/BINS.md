# Sortierkästen, Einsätze und die Bin-Druckdatei (seit 1.1.0)

## Einsätze verschieben (Drag & Drop)
Kastenseite → Draufsicht → **„Einsätze verschieben“** einschalten → Einsatz ziehen und auf freien Zellen
loslassen. Das Raster rastet ein, die Größe bleibt, die Zellen werden geprüft (Griff, Rand, belegt).
Server: `POST /n/<Kasten>/bins/<Einsatz>/move` (`cells=A1,B1`), `kasten.move_bin`. Der Einsatz bekommt
„Etikett ungedruckt“ (Position steht auf dem Tag). Funktioniert mit Maus und Touch; bei jeder
Drehung der Ansicht.

## Parameter je Einsatz
Einsatzseite → **Druck-Parameter (3D-Generator)**: Etikettenablage 40×12, Greifmulde, Wand, Boden,
Trennwand, Rastermaß, Eckenradius, Formschräge, Fase. Nur Abweichungen vom Standard werden gespeichert
(`container.cad`, JSON); Standardwerte siehe `kasten.CAD_FIELDS`.

## Bin-Druckdatei `bins.json`
Eine Datei für den **parametrischen Druckgenerator**: `Drucken → Dateien → bins.json` oder
`GET /labels/bins.json` (eine Kopie liegt in `data/druck/bins.json`). Inhalt (`format: kp-lager-bins/1`):

```json
{
  "format": "kp-lager-bins/1",
  "boxes": [{
    "code": "SOR-001", "model": "norb16", "grid": {"cols": 5, "rows": 7}, "blocked": ["C1","D1","E1"],
    "bins": [{
      "code": "BIN-001", "position": "B2", "cells": ["B2","C2"],
      "size": "2x1", "units": {"w": 1, "d": 2}, "divisions": {"x": 3, "y": 1},
      "params": {"label": true, "wall": 1.2, "scoop": 15.0, "...": "..."},
      "compartments": [{"position": "A1", "label": "M3 Muttern"}],
      "label_text": "M3 Muttern, …", "command": "uv run --group cad python cad/norb_bins.py 2x1 --div 3x1"
    }]
  }]
}
```

Erzeugen aller Einsätze (STEP + STL, gleiche Einsätze nur einmal):

```bash
uv run --group cad python cad/norb_bins.py --file bins.json --out out/bins
```

`cad/norb_bins.py` liest Größe, Teilung und `params`; abweichende Parameter stehen im Dateinamen
(z. B. `Bin_2x1_div3x1_wall1.6`). Das Rastermaß 54,77 mm, Höhe 45,5 mm usw. siehe `docs/NORB16.md`.

## Seitenetiketten
Siehe `docs/A4.md` (Bin-Etikett-Editor, A4-Warteschlange).
