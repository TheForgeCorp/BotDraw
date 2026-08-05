"""Plotter-safe linetype geometry + Design engine linetype knobs."""

from __future__ import annotations

from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.core.optimize import optimize_layered
from botdraw.palettes import load_palette
from botdraw.styles import ensure_styles_loaded, get_style
from botdraw.styles.geom import LINE_TYPES, stroke_linetype


def test_stroke_linetype_solid_passthrough():
    pts = [(0.0, 0.0), (40.0, 0.0)]
    out = stroke_linetype(pts, linetype="solid")
    assert len(out) == 1
    assert out[0][0] == pts
    assert out[0][1] is False


def test_stroke_linetype_dashed_increases_strokes_and_gaps():
    pts = [(0.0, 0.0), (60.0, 0.0)]
    dashed = stroke_linetype(pts, linetype="dashed", density=1.0, pattern_width_mm=4.0)
    assert len(dashed) > 1
    # Gaps between consecutive dash ends/starts should exceed linemerge tol
    for (a, _), (b, _) in zip(dashed, dashed[1:]):
        gap = abs(b[0][0] - a[-1][0])
        assert gap > 0.2


def test_stroke_linetype_dotted_and_dash_dot():
    pts = [(0.0, 0.0), (50.0, 0.0)]
    dotted = stroke_linetype(pts, linetype="dotted", density=1.2, pattern_width_mm=3.0)
    assert len(dotted) >= 3
    assert all(len(p) == 2 for p, _ in dotted)

    dash_dot = stroke_linetype(pts, linetype="dash_dot", density=1.0, pattern_width_mm=4.0)
    assert len(dash_dot) > 1


def test_stroke_linetype_double_two_offsets():
    pts = [(0.0, 0.0), (30.0, 0.0)]
    out = stroke_linetype(pts, linetype="double", pattern_width_mm=2.0)
    assert len(out) == 2
    # Parallel offsets should be separated in Y for a horizontal segment
    y0 = out[0][0][0][1]
    y1 = out[1][0][0][1]
    assert abs(y0 - y1) > 0.5


def test_line_types_constant():
    assert set(LINE_TYPES) == {"solid", "dashed", "dotted", "dash_dot", "double"}


def test_modular_chords_linetype_and_authoritative_n():
    ensure_styles_loaded()
    palette = load_palette("default-6")
    solid = get_style("modular_chords").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=3.0,  # must not change N
            extra={"n_points": 80, "k": 17, "linetype": "solid"},
        ),
        paper=PaperSize.A5,
    )
    assert solid.meta["n_points"] == 80
    assert solid.meta["strokes"] == 80
    assert solid.meta["linetype"] == "solid"

    dashed = get_style("modular_chords").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            extra={
                "n_points": 80,
                "k": 17,
                "linetype": "dashed",
                "line_density": 1.2,
                "line_pattern_width_mm": 3.0,
            },
        ),
        paper=PaperSize.A5,
    )
    assert dashed.meta["n_points"] == 80
    assert dashed.meta["linetype"] == "dashed"
    assert dashed.meta["line_density"] == 1.2
    assert dashed.meta["line_pattern_width_mm"] == 3.0
    assert dashed.meta["strokes"] > solid.meta["strokes"]

    # Dashes must survive optimize without being glued back into one chord each
    opt = optimize_layered(dashed)
    assert sum(len(p.polylines) for p in opt.passes) == dashed.meta["strokes"]


def test_rule30_linetype_and_authoritative_grid():
    ensure_styles_loaded()
    palette = load_palette("default-6")
    solid = get_style("rule30").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=2.5,
            extra={"cols": 60, "rows": 40, "rule": 30, "linetype": "solid"},
        ),
        paper=PaperSize.A5,
    )
    assert solid.meta["cols"] == 60
    assert solid.meta["rows"] == 40

    dashed = get_style("rule30").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            extra={
                "cols": 60,
                "rows": 40,
                "rule": 30,
                "linetype": "dashed",
                "line_pattern_width_mm": 2.5,
                "line_density": 1.0,
            },
        ),
        paper=PaperSize.A5,
    )
    assert dashed.meta["linetype"] == "dashed"
    assert dashed.meta["strokes"] >= solid.meta["strokes"]


def test_prime_sieve_linetype_and_mark_size():
    ensure_styles_loaded()
    palette = load_palette("default-6")
    layered = get_style("prime_sieve").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=3.0,  # must not change max_n
            extra={
                "max_n": 100,
                "grid_cols": 6,
                "show_arcs": True,
                "show_sieve": True,
                "mark_size_mm": 3.0,
                "linetype": "dotted",
                "line_density": 1.0,
                "line_pattern_width_mm": 2.0,
            },
        ),
        paper=PaperSize.A5,
    )
    assert layered.meta["max_n"] == 100
    assert layered.meta["mark_size_mm"] == 3.0
    assert layered.meta["linetype"] == "dotted"
    assert layered.meta["strokes"] > 0
    assert len(layered.passes) == 2
