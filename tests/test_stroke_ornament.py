"""Stroke ornament line types."""

from __future__ import annotations

from botdraw.core.models import LayeredSVG, Polyline
from botdraw.core.svg import make_pass
from botdraw.portrait.ornament import LINE_TYPES, StrokeOrnamentParams, decorate_layered, decorate_polyline


def _sample_layered():
    poly = Polyline(points=[(10.0, 10.0), (50.0, 10.0), (90.0, 40.0)], pen_id="black")
    return LayeredSVG(
        width_mm=100,
        height_mm=100,
        passes=[make_pass("edges", "Portrait edges", "black", [poly])],
        meta={"quality": "booth-fast"},
    )


def test_all_line_types_emit_geometry():
    base = Polyline(points=[(0.0, 0.0), (40.0, 0.0), (80.0, 20.0)], pen_id="ink")
    for lt in LINE_TYPES:
        params = StrokeOrnamentParams(line_type=lt, pattern_amplitude_mm=1.0, pattern_period_mm=2.0)
        out = decorate_polyline(base, params)
        assert out, f"{lt} produced nothing"
        assert all(len(p.points) >= 2 for p in out)


def test_dashed_respects_dash_gap():
    base = Polyline(points=[(0.0, 0.0), (100.0, 0.0)], pen_id="ink")
    params = StrokeOrnamentParams(line_type="dashed", dash_mm=5.0, gap_mm=5.0)
    out = decorate_polyline(base, params)
    assert len(out) >= 2


def test_wave_amplitude_increases_path_length():
    base = Polyline(points=[(0.0, 0.0), (60.0, 0.0)], pen_id="ink")
    flat = decorate_polyline(base, StrokeOrnamentParams(line_type="wave", pattern_amplitude_mm=0.0))
    wavy = decorate_polyline(base, StrokeOrnamentParams(line_type="wave", pattern_amplitude_mm=3.0))

    def plen(polys):
        total = 0.0
        for p in polys:
            for i in range(1, len(p.points)):
                x0, y0 = p.points[i - 1]
                x1, y1 = p.points[i]
                total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return total

    assert plen(wavy) >= plen(flat)


def test_decorate_layered_respects_budget():
    layered = _sample_layered()
    # Many zigzag expansions still capped
    out = decorate_layered(
        layered,
        StrokeOrnamentParams(line_type="zigzag", max_paths=5, pattern_amplitude_mm=1.0),
    )
    n = sum(len(p.polylines) for p in out.passes)
    assert n <= 5
