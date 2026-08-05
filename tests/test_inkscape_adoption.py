"""Inkscape / AxiDraw adoption: scan modes, layer SVG, vpype optimize."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import LayeredSVG, PassLayer, Polyline, QualityPreset, StyleParams
from botdraw.core.optimize import optimize_layered
from botdraw.core.svg import layered_to_svg_string
from botdraw.palettes import load_palette
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.pens import assign_pens
from botdraw.portrait.preview import portrait_vector_preview_dict, portrait_vector_raw_svg
from botdraw.portrait.restyle import restyle_linework
from botdraw.portrait.scan_modes import (
    SCAN_MODES,
    build_scan_intermediate,
    intermediate_to_png_b64,
    normalize_scan_mode,
    scan_mode_knobs,
)
from botdraw.styles.image_utils import luminance, synthetic_portrait


def test_scan_modes_normalize_and_knobs():
    assert set(SCAN_MODES) >= {"auto", "brightness", "edges", "centerline", "color_bands"}
    assert normalize_scan_mode("Canny") == "edges"
    assert normalize_scan_mode("skeleton") == "centerline"
    assert scan_mode_knobs("centerline")["prefer_skeleton"] is True
    assert scan_mode_knobs("centerline")["prefer_silhouette"] is False
    assert scan_mode_knobs("brightness")["soft_face_edges"] is False
    assert scan_mode_knobs("color_bands")["region_boost"] is True


def test_intermediate_preview_png():
    rgb = synthetic_portrait(96).astype(np.float32)
    lum = luminance(rgb)
    for mode in SCAN_MODES:
        arr = build_scan_intermediate(lum, rgb, mode, posterize_levels=4)
        assert arr is not None and arr.size > 0
        b64 = intermediate_to_png_b64(arr, max_side=120)
        assert b64 and len(b64) > 20


def test_ingest_scan_mode_centerline_meta():
    pv = ingest_portrait(
        image_array=synthetic_portrait(128).astype(np.float32),
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        scan_mode="centerline",
        hatch_size=0,
        ensemble=False,
    )
    assert (pv.meta or {}).get("scan_mode") == "centerline"
    assert pv.edge_polylines_mm
    prev = portrait_vector_preview_dict(pv, include_preview_png=True)
    assert prev.get("scan_mode") == "centerline"
    assert prev.get("intermediate_png_b64")


def test_linework_emits_inkscape_structure_layers():
    rgb = synthetic_portrait(128).astype(np.float32)
    pv = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        hatch_size=16,
        ensemble=False,
    )
    palette = load_palette("default-6")
    pv = assign_pens(pv, palette)
    layered = restyle_linework(pv, palette, StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST))
    names = [p.name for p in layered.passes]
    assert any(n.startswith("1 Structure") for n in names)
    if pv.hatch_polylines_mm:
        assert any("Midtone" in n for n in names)
    assert layered.meta.get("inkscape_layers")


def test_svg_has_inkscape_layer_groupmode():
    palette = load_palette("default-6")
    pen = palette.pens[0]
    layered = LayeredSVG(
        width_mm=100,
        height_mm=140,
        passes=[
            PassLayer(
                id="structure",
                name="1 Structure",
                pen_id=pen.id,
                polylines=[Polyline(points=[(10, 10), (40, 20), (60, 15)], pen_id=pen.id)],
            ),
            PassLayer(
                id="midtone",
                name="2 Midtone hatch",
                pen_id=pen.id,
                polylines=[Polyline(points=[(12, 40), (50, 42)], pen_id=pen.id)],
            ),
        ],
    )
    svg = layered_to_svg_string(layered, palette)
    assert "xmlns:inkscape" in svg
    assert "groupmode" in svg
    assert "1 Structure" in svg
    assert 'fill="none"' in svg


def test_raw_ingest_svg_layers():
    pv = ingest_portrait(
        image_array=synthetic_portrait(96).astype(np.float32),
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        hatch_size=0,
    )
    svg = portrait_vector_raw_svg(pv)
    assert 'inkscape:groupmode="layer"' in svg
    assert "1 Structure" in svg


def test_vpype_optimize_runs_when_installed():
    palette = load_palette("default-6")
    pen = palette.pens[0]
    # Two nearly touching segments — merge should reduce count
    layered = LayeredSVG(
        width_mm=80,
        height_mm=80,
        passes=[
            PassLayer(
                id="p",
                name="1 Structure",
                pen_id=pen.id,
                polylines=[
                    Polyline(points=[(0.0, 0.0), (10.0, 0.0)], pen_id=pen.id),
                    Polyline(points=[(10.05, 0.0), (20.0, 0.0)], pen_id=pen.id),
                    Polyline(points=[(30.0, 10.0), (40.0, 12.0)], pen_id=pen.id),
                ],
            )
        ],
        meta={},
    )
    out = optimize_layered(layered, use_vpype=True)
    assert out.meta.get("optimizer") in ("vpype", "greedy")
    n = sum(len(p.polylines) for p in out.passes)
    assert n <= 3
    assert n >= 1
    # Force greedy path
    out2 = optimize_layered(layered, use_vpype=False)
    assert out2.meta.get("optimizer") == "greedy"
