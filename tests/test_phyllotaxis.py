"""Phyllotaxis Design Library — knobs, marks, and params_extra plumbing."""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.styles import ensure_styles_loaded, get_style
from botdraw.styles.design_library import GOLDEN_ANGLE_DEG, phyllotaxis_points
from botdraw.styles.geom import MARK_KINDS, mark_polyline, mark_polylines


def _render(extra: dict, *, density: float = 1.0):
    ensure_styles_loaded()
    palette = load_palette("default-6")
    return get_style("phyllotaxis").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_BALANCED,
            density=density,
            extra=extra,
        ),
        paper=PaperSize.A4,
    )


def test_angle_changes_geometry():
    a = phyllotaxis_points(5, angle_deg=137.5, scale=1.0)
    b = phyllotaxis_points(5, angle_deg=90.0, scale=1.0)
    assert a[1] != b[1]
    layered_a = _render({"n_points": 120, "angle_deg": 137.5, "mark_size_mm": 2.5})
    layered_b = _render({"n_points": 120, "angle_deg": 90.0, "mark_size_mm": 2.5})
    assert layered_a.meta["angle_deg"] == 137.5
    assert layered_b.meta["angle_deg"] == 90.0
    pa = layered_a.passes[0].polylines[1].points[0]
    pb = layered_b.passes[0].polylines[1].points[0]
    assert math.hypot(pa[0] - pb[0], pa[1] - pb[1]) > 0.5


def test_n_points_authoritative_not_scaled_by_density():
    layered = _render({"n_points": 200, "angle_deg": GOLDEN_ANGLE_DEG, "mark_size_mm": 2.5}, density=2.0)
    assert layered.meta["n_points"] == 200
    assert layered.meta["strokes"] == 200
    assert sum(len(p.polylines) for p in layered.passes) == 200


def test_mark_glyphs():
    for kind in MARK_KINDS:
        layered = _render({"n_points": 80, "mark": kind, "mark_size_mm": 3.0})
        assert layered.meta["mark"] == kind
        assert layered.meta["mark_size_mm"] == 3.0
        expected = 160 if kind == "cross" else 80
        assert layered.meta["strokes"] == expected
        poly = layered.passes[0].polylines[0]
        assert len(poly.points) >= 2
        if kind == "cross":
            assert poly.closed is False
        else:
            assert poly.closed is True

    star = mark_polyline(0, 0, 1.0, "star")
    square = mark_polyline(0, 0, 1.0, "square")
    assert len(star) == 11
    assert len(square) == 5
    assert len(mark_polylines(0, 0, 1.0, "cross")) == 2


def test_api_params_extra_changes_phyllotaxis():
    client = TestClient(app)
    default = client.post(
        "/api/render",
        json={
            "app": "design",
            "style_id": "phyllotaxis",
            "palette_id": "default-6",
            "paper": "A5",
            "quality": "booth-fast",
            "seed": 3,
            "density": 1.0,
            "params_extra": {"n_points": 900, "angle_deg": 137.5, "mark": "circle", "mark_size_mm": 2.5},
        },
    )
    custom = client.post(
        "/api/render",
        json={
            "app": "design",
            "style_id": "phyllotaxis",
            "palette_id": "default-6",
            "paper": "A5",
            "quality": "booth-fast",
            "seed": 3,
            "density": 1.0,
            "params_extra": {"n_points": 180, "angle_deg": 90.0, "mark": "star", "mark_size_mm": 3.5},
        },
    )
    assert default.status_code == 200
    assert custom.status_code == 200
    d_meta = default.json()["layers"]["meta"]
    c_meta = custom.json()["layers"]["meta"]
    assert d_meta["n_points"] == 900
    assert c_meta["n_points"] == 180
    assert c_meta["angle_deg"] == 90.0
    assert c_meta["mark"] == "star"
    assert c_meta["mark_size_mm"] == 3.5
    assert custom.json()["layers"]["passes"][0]["polyline_count"] == 180
    assert default.json()["emulator"]["stats"]["stroke_count"] != custom.json()["emulator"]["stats"]["stroke_count"]
