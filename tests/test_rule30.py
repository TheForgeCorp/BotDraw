"""Rule 30 cellular automaton — Design Library (Math Derived)."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.styles import ensure_styles_loaded, get_style
from botdraw.styles.design_library import evolve_rule30


def test_rule30_evolution_known_rows():
    """Single center seed → classic Rule 30 first rows (no wrap)."""
    cols = 15
    grid = evolve_rule30(cols, 5, rule=30)
    c = cols // 2
    # Row 0: single 1 at center
    assert list(grid[0]) == [1 if i == c else 0 for i in range(cols)]
    # Row 1: three 1s centered on seed (001 / 010 / 100 → live)
    assert list(grid[1, c - 1 : c + 2]) == [1, 1, 1]
    # Bitmask check: rule 30 = 0b00011110
    assert 30 == 0b00011110
    # Interior chaos: later rows have mixed live/dead (not all-zero, not all-one)
    assert 0 < int(grid[4].sum()) < cols


def test_rule30_style_registered_and_renders():
    ensure_styles_loaded()
    eng = get_style("rule30")
    assert eng.category == "design"
    assert eng.name == "Rule 30"
    palette = load_palette("default-6")
    layered = eng.render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_BALANCED,
            density=1.0,
            extra={"cols": 120, "rows": 90, "rule": 30},
        ),
        paper=PaperSize.A4,
    )
    assert layered.meta["style"] == "rule30"
    assert layered.meta["subsection"] == "math_derived"
    assert layered.meta["cols"] == 120
    assert layered.meta["rows"] == 90
    assert layered.meta["rule"] == 30
    assert layered.meta["live_cells"] > 0
    assert layered.passes
    n_polys = sum(len(p.polylines) for p in layered.passes)
    assert n_polys > 0
    assert n_polys == layered.meta["strokes"]


def test_rule30_listed_under_design_category():
    ensure_styles_loaded()
    from botdraw.styles import list_styles

    ids = {s["id"] for s in list_styles(category="design")}
    assert "rule30" in ids
