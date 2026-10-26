"""Bin-Generator (nur mit `uv run --group cad pytest`, sonst übersprungen)."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("build123d")
sys.path.insert(0, str(Path(__file__).parents[1] / "cad"))

import norb_bins as nb  # noqa: E402
from build123d import Vector  # noqa: E402


def test_1x1_label_dimensions_and_pocket() -> None:
    spec = nb.BinSpec(1, 1)
    part = nb.build(spec)
    bb = part.bounding_box()
    assert part.is_valid and len(part.solids()) == 1
    assert (round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)) == (54.77, 54.77, 45.5)
    shelf_mid_y = spec.size_y / 2 - spec.wall - spec.shelf_depth / 2
    assert not part.is_inside(Vector(0, shelf_mid_y, 44.9))  # Etikettenmulde ist leer
    assert part.is_inside(Vector(0, shelf_mid_y, 44.0))  # darunter massive Ablage
    assert part.is_inside(Vector(0, 0, 0.6))  # Boden ohne Rille


def test_depth_two_has_groove_width_two_not() -> None:
    deep = nb.build(nb.BinSpec(1, 2, label=False))
    wide = nb.build(nb.BinSpec(2, 1, label=False))
    assert not deep.is_inside(Vector(0, 0, 1.0))  # Rille an der Rastergrenze
    assert not deep.is_inside(Vector(0, 0, 6.5))  # Spitzbogen-Decke (kein flacher Steg)
    assert deep.is_inside(Vector(0, 0, 8.0))  # Gehäuse über der Spitze
    assert wide.is_inside(Vector(0, 0, 0.6))  # Breite allein: keine Rille


def test_dividers_and_names(tmp_path: Path) -> None:
    spec = nb.BinSpec(2, 1, div_x=3)
    part = nb.build(spec)
    x = -spec.size_x / 2 + spec.size_x / 3
    assert part.is_inside(Vector(x, 0, 20))  # Trennwand
    assert not part.is_inside(Vector(x + 5, 0, 20))  # Fach
    assert spec.name == "Bin_2x1_div3x1_label"
    files = nb.export(nb.BinSpec(1, 1, label=False), tmp_path)
    assert [f.suffix for f in files] == [".step", ".stl"] and all(
        f.stat().st_size > 1000 for f in files
    )


def test_too_small_for_label_rejected() -> None:
    with pytest.raises(ValueError):
        nb.build(nb.BinSpec(1, 1, pitch=40))


def test_scoop_and_rounded_floor() -> None:
    spec = nb.BinSpec(1, 1, label=False)
    part = nb.build(spec)
    front = -spec.size_y / 2 + nb._draft_inset(spec, spec.floor + spec.scoop) + spec.wall
    assert part.is_inside(Vector(0, front + 2, spec.floor + 5))  # Mulde füllt die Ecke
    assert not part.is_inside(
        Vector(0, front + spec.scoop, spec.floor + spec.scoop)
    )  # Kreismitte frei
    no_scoop = nb.build(nb.BinSpec(1, 1, label=False, scoop=0, floor_fillet=0))
    assert not no_scoop.is_inside(Vector(0, front + 2, spec.floor + 5))
