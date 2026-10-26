"""Parametrische Einsätze (Bins) für Kistenberg NORB16 – STEP + STL mit build123d.

Maße aus den vorhandenen Bins vermessen (docs/NORB16.md): Raster 54,77 mm je Einheit,
Höhe fest 45,5 mm, Wand/Boden 1,2 mm, ~3° Formschräge, 3 mm Fase unten.
Breite (X) läuft parallel zu den Bodenrippen der Box. Bins mit Tiefe (Y) > 1 kreuzen Rippen
und bekommen an jeder inneren Rastergrenze eine Rille.
Optional Etikettenablage 40×12 mm an der Rückwand.

Beispiele:
  uv run --group cad python cad/norb_bins.py 2x2 --div 3x1
  uv run --group cad python cad/norb_bins.py --standard
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from build123d import (
    Axis,
    Box,
    Cylinder,
    Part,
    Plane,
    Polygon,
    Pos,
    RectangleRounded,
    export_step,
    export_stl,
    extrude,
    fillet,
    loft,
)

HEIGHT = 45.5  # fest (Box-Innenhöhe)


@dataclass(frozen=True)
class BinSpec:
    w: int  # Einheiten in X (parallel zu den Rippen)
    d: int  # Einheiten in Y (kreuzt Rippen -> Rillen)
    div_x: int = 1  # Fächer nebeneinander (Trennwände quer zu X)
    div_y: int = 1  # Fächer hintereinander
    label: bool = True  # Ablage für 40×12-Etikett an der Rückwand
    pitch: float = 54.77
    wall: float = 1.2
    floor: float = 1.2
    corner: float = 3.0
    draft: float = 2.3  # Einzug je Seite unten ggü. oben (Formschräge)
    chamfer: float = 3.0  # Fase an der Unterkante
    groove_bottom: float = 9.8  # Rillenbreite unten
    groove_top: float = 5.0  # Rillenbreite oben
    groove_height: float = 4.6
    divider: float = 1.2
    divider_drop: float = 2.0  # Trennwände so viel unter Oberkante
    label_w: float = 40.0
    label_h: float = 12.0
    label_margin: float = 0.3  # Spiel um das Etikett
    label_depth: float = 0.6  # Tiefe der Etikettenmulde
    shelf_depth: float = 15.0  # Tiefe der Ablage (Y)
    shelf_thickness: float = 2.0
    inner_radius: float = 5.0  # senkrechte Innenecken
    floor_fillet: float = 2.5  # Übergang Boden/Wand innen
    scoop: float = 15.0  # Greifmulde vorn (Radius), 0 = aus

    @property
    def size_x(self) -> float:
        return self.w * self.pitch

    @property
    def size_y(self) -> float:
        return self.d * self.pitch

    @property
    def name(self) -> str:
        parts = [f"Bin_{self.w}x{self.d}"]
        if self.div_x > 1 or self.div_y > 1:
            parts.append(f"div{self.div_x}x{self.div_y}")
        if self.label:
            parts.append("label")
        return "_".join(parts)


def _section(
    spec: BinSpec, z: float, inset: float, radius: float | None = None
) -> RectangleRounded:
    r = radius if radius is not None else spec.corner
    sk = RectangleRounded(spec.size_x - 2 * inset, spec.size_y - 2 * inset, r)
    return Plane.XY.offset(z) * sk


def _draft_inset(spec: BinSpec, z: float) -> float:
    return spec.draft * (1 - z / HEIGHT)


def _outer(spec: BinSpec) -> Part:
    c = spec.chamfer
    return loft(
        [
            _section(spec, 0, _draft_inset(spec, 0) + c),
            _section(spec, c, _draft_inset(spec, c)),
            _section(spec, HEIGHT, 0),
        ],
        ruled=True,
    )


def _cavity(spec: BinSpec) -> Part:
    c, t, ri = spec.chamfer, spec.wall, spec.inner_radius
    z0 = spec.floor
    cavity = loft(
        [
            _section(spec, z0, _draft_inset(spec, 0) + c + t, ri),
            _section(spec, c + t, _draft_inset(spec, c + t) + t, ri),
            _section(spec, HEIGHT + 1, _draft_inset(spec, HEIGHT + 1) + t, ri),
        ],
        ruled=True,
    )
    if spec.floor_fillet > 0:  # gerundeter Boden – Kleinteile sammeln sich nicht in Kanten
        bottom = cavity.edges().group_by(Axis.Z)[0]
        cavity = fillet(bottom, radius=spec.floor_fillet)
    return cavity


def _groove_prism(spec: BinSpec, y: float, grow: float, extra_h: float) -> Part:
    """Trapez-Prisma entlang X an Position y (grow/extra_h > 0 = Gehäuse um die Rille)."""
    hb = spec.groove_bottom / 2 + grow
    ht = spec.groove_top / 2 + grow
    h = spec.groove_height + extra_h
    # Spitzbogen-Decke (45°) statt flacher Brücke -> ohne Support druckbar
    profile = Polygon((-hb, -0.01), (hb, -0.01), (ht, h), (0, h + ht), (-ht, h), align=None)
    prism = extrude(Plane.YZ * profile, amount=spec.size_x, both=True)
    return Pos(0, y, 0) * prism


def _dividers(spec: BinSpec) -> Part | None:
    top = HEIGHT - spec.divider_drop
    parts = []
    for i in range(1, spec.div_x):
        x = -spec.size_x / 2 + i * spec.size_x / spec.div_x
        parts.append(Pos(x, 0, top / 2) * Box(spec.divider, spec.size_y, top))
    for j in range(1, spec.div_y):
        y = -spec.size_y / 2 + j * spec.size_y / spec.div_y
        parts.append(Pos(0, y, top / 2) * Box(spec.size_x, spec.divider, top))
    if not parts:
        return None
    result = parts[0]
    for p in parts[1:]:
        result = result + p
    return result


def _label_shelf(spec: BinSpec) -> tuple[Part, Part]:
    """Ablage an der Rückwand (+Y) mit 45°-Stütze (druckbar ohne Support) und Etikettenmulde."""
    t = spec.wall
    back = spec.size_y / 2 - t  # Innenkante Rückwand (oben)
    front = back - spec.shelf_depth
    top = HEIGHT - 0.4
    under = top - spec.shelf_thickness
    profile = Polygon(
        (back + t, top), (front, top), (front, under), (back + t, under - spec.shelf_depth - t),
        align=None,
    )  # fmt: skip
    shelf = extrude(Plane.YZ * profile, amount=spec.size_x, both=True)
    pw = spec.label_w + 2 * spec.label_margin
    ph = spec.label_h + 2 * spec.label_margin
    pocket = Pos(0, (back + front) / 2, top) * Box(pw, ph, 2 * spec.label_depth)
    return shelf, pocket


def _scoops(spec: BinSpec) -> Part | None:
    """Greifmulden: Viertelkreis-Rundung zwischen Boden und Vorderwand jeder Fachreihe."""
    if spec.scoop <= 0:
        return None
    row_depth = spec.size_y / spec.div_y
    r = min(spec.scoop, row_depth * 0.5)
    z0 = spec.floor
    fronts = [-spec.size_y / 2 + _draft_inset(spec, z0 + r) + spec.wall]
    fronts += [-spec.size_y / 2 + j * row_depth + spec.divider / 2 for j in range(1, spec.div_y)]
    parts = []
    for y in fronts:
        block = Pos(0, y + r / 2 - 2.5, z0 + r / 2) * Box(spec.size_x, r + 5, r)
        cyl = Pos(0, y + r, z0 + r) * (Plane.YZ * Cylinder(r, spec.size_x + 2))
        parts.append(block - cyl)
    result = parts[0]
    for p in parts[1:]:
        result = result + p
    return result


def build(spec: BinSpec) -> Part:
    if spec.w < 1 or spec.d < 1:
        raise ValueError("Mindestens 1x1")
    if spec.label and spec.size_x - 2 * (spec.wall + spec.draft) < spec.label_w + 2:
        raise ValueError("Bin zu schmal für das Etikett")
    outer = _outer(spec)
    cavity = _cavity(spec)
    body = outer - cavity
    inner_volume = outer & cavity  # Hohlraum innerhalb der Außenhülle
    if (div := _dividers(spec)) is not None:
        body = body + (div & inner_volume)
    if (scoop := _scoops(spec)) is not None:
        body = body + (scoop & inner_volume)
    if spec.label:
        shelf, pocket = _label_shelf(spec)
        body = body + (shelf & outer)
        body = body - pocket
    for k in range(1, spec.d):  # Rillen an inneren Rastergrenzen (quer zur Tiefe)
        y = -spec.size_y / 2 + k * spec.pitch
        housing = _groove_prism(spec, y, grow=spec.wall, extra_h=spec.floor)
        body = body + (housing & outer)
        body = body - _groove_prism(spec, y, grow=0, extra_h=0)
    return body


def export(spec: BinSpec, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    part = build(spec)
    step, stl = out / f"{spec.name}.step", out / f"{spec.name}.stl"
    export_step(part, str(step))
    export_stl(part, str(stl), tolerance=0.05, angular_tolerance=0.2)
    return [step, stl]


STANDARD = [  # Standard-Einsätze NORB16
    BinSpec(1, 1), BinSpec(1, 1, div_x=2), BinSpec(1, 1, div_x=3),
    BinSpec(2, 1), BinSpec(2, 1, div_x=3), BinSpec(2, 1, div_x=5),
    BinSpec(1, 2), BinSpec(1, 2, div_y=2), BinSpec(1, 2, div_x=3),
    BinSpec(2, 2), BinSpec(2, 2, div_x=2), BinSpec(2, 2, div_x=3, div_y=2),
]  # fmt: skip


def _pair(text: str) -> tuple[int, int]:
    a, _, b = text.lower().partition("x")
    return int(a), int(b or 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("size", nargs="?", help="Größe BxT in Rastereinheiten, z. B. 2x1")
    ap.add_argument("--div", default="1x1", help="Fächer BxT, z. B. 3x1")
    ap.add_argument("--no-label", action="store_true", help="ohne Etikettenablage")
    ap.add_argument("--pitch", type=float, default=BinSpec.pitch, help="Rastermaß in mm")
    ap.add_argument("--standard", action="store_true", help="Standard-Set erzeugen")
    ap.add_argument("--out", type=Path, default=Path("out/bins"))
    args = ap.parse_args()
    if args.standard:
        specs = STANDARD
    elif args.size:
        (w, d), (dx, dy) = _pair(args.size), _pair(args.div)
        specs = [BinSpec(w, d, dx, dy, label=not args.no_label, pitch=args.pitch)]
    else:
        ap.error("Größe angeben oder --standard")
    for spec in specs:
        for path in export(spec, args.out):
            print(path)


if __name__ == "__main__":
    main()
