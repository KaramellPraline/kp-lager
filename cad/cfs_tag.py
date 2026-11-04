"""CFS-NFC-Platte: Träger für einen MIFARE-Classic-1K-Coin-Tag (Creality CFS).

Mit Etikettenmulde und Klebelasche.

Aufbau (Z = 0 ist die Rückseite, die später an der Spule klebt):
  - Platte 46 × 42 × 2,4 mm mit Eckenradius
  - Rückseite: runde Tasche für den NFC-Tag (Ø 25,4 × 1,3 mm, Standard-Coin 25 mm + Spiel)
  - Vorderseite: Mulde 40 × 12 × 0,4 mm für das aufgeklebte D30-Etikett (12 × 40)
  - Klebelasche: 0,8 mm dünn, bündig mit der Rückseite, seitlich 20 mm lang → auf die
    Spulenflanke kleben, der Tag liegt dann geschützt zwischen Platte und Spule

Drucken: Rückseite (Tasche + Lasche) auf das Druckbett, 0,2 mm Schicht, PLA/PETG; die Tasche wird
überbrückt. Tag einlegen, Platte mit der Lasche auf die Spule kleben, Etikett in die Mulde.

Beispiele:
  uv run --group cad python cad/cfs_tag.py
  uv run --group cad python cad/cfs_tag.py --tab 25 --coin 30 --out out/cfs
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from build123d import Box, Cylinder, Part, Pos, RectangleRounded, export_step, export_stl, extrude


@dataclass(frozen=True)
class CfsSpec:
    w: float = 46.0  # Platte X
    h: float = 42.0  # Platte Y
    t: float = 2.4  # Plattendicke
    corner: float = 3.0
    coin_d: float = 25.4  # Tag-Tasche (Coin 25 mm + Spiel)
    coin_depth: float = 1.3
    coin_y: float = -7.5  # Mittelpunkt der Tasche
    label_w: float = 40.0
    label_h: float = 12.0
    label_depth: float = 0.4
    label_y: float = 13.0  # Mittelpunkt der Etikettenmulde
    tab_len: float = 20.0  # Klebelasche, Länge über den Plattenrand hinaus
    tab_h: float = 30.0
    tab_t: float = 0.8

    @property
    def name(self) -> str:
        return f"cfs_platte_{self.coin_d:g}mm_lasche{self.tab_len:g}"


def check(spec: CfsSpec) -> None:
    """Maße prüfen, damit Tasche, Mulde und Wand zusammenpassen."""
    r = spec.coin_d / 2
    if spec.coin_y - r < -spec.h / 2 + 0.8 or spec.coin_y + r > spec.h / 2 - 0.8:
        raise ValueError("Tag-Tasche liegt zu nah am Rand (mind. 0,8 mm Wand)")
    if abs(spec.coin_y - spec.label_y) < r + spec.label_h / 2 + 0.6:
        raise ValueError("Tag-Tasche und Etikettenmulde überschneiden sich")
    if spec.label_y + spec.label_h / 2 > spec.h / 2 - 0.8 or spec.label_w > spec.w - 2.4:
        raise ValueError("Etikettenmulde passt nicht auf die Platte")
    if spec.t - spec.coin_depth < 0.8:
        raise ValueError("Zu wenig Material über dem Tag (mind. 0,8 mm)")
    if spec.tab_t >= spec.coin_depth or spec.tab_len <= 0 or spec.tab_h > spec.h:
        raise ValueError("Klebelasche passt nicht")


def build(spec: CfsSpec) -> Part:
    check(spec)
    plate = extrude(RectangleRounded(spec.w, spec.h, spec.corner), spec.t)  # Z 0 … t
    # Klebelasche an der +X-Seite, bündig mit der Rückseite (Z 0 … tab_t)
    tab = Pos(spec.w / 2 + spec.tab_len / 2 - 0.5, 0, spec.tab_t / 2) * Box(
        spec.tab_len + 1.0, spec.tab_h, spec.tab_t
    )
    body = plate + tab
    # Tag-Tasche von der Rückseite
    pocket = Pos(0, spec.coin_y, spec.coin_depth / 2 - 0.01) * Cylinder(
        spec.coin_d / 2, spec.coin_depth + 0.02
    )
    body = body - pocket
    # Etikettenmulde von der Vorderseite
    dish = Pos(0, spec.label_y, spec.t - spec.label_depth / 2 + 0.01) * Box(
        spec.label_w, spec.label_h, spec.label_depth + 0.02
    )
    return body - dish


def export(spec: CfsSpec, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    part = build(spec)
    step, stl = out / f"{spec.name}.step", out / f"{spec.name}.stl"
    export_step(part, str(step))
    export_stl(part, str(stl), tolerance=0.02, angular_tolerance=0.1)
    return [step, stl]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--coin", type=float, default=CfsSpec.coin_d, help="Tag-Durchmesser inkl. Spiel in mm"
    )
    ap.add_argument(
        "--tab", type=float, default=CfsSpec.tab_len, help="Länge der Klebelasche in mm"
    )
    ap.add_argument("--out", type=Path, default=Path("out/cfs"))
    args = ap.parse_args()
    for path in export(CfsSpec(coin_d=args.coin, tab_len=args.tab), args.out):
        print(path)


if __name__ == "__main__":
    main()
