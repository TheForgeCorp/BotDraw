"""Linedraw portrait QA: midtone hatch + smooth contours."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.models import QualityPreset
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.linedraw_edges import contours_from_lum, hatch_from_lum, linedraw_edges_and_hatch
from botdraw.styles.image_utils import luminance, synthetic_portrait

client = TestClient(app)


def _dark_bg_bright_face(size: int = 160) -> np.ndarray:
    """Dark border (wall) + brighter face disk — mirrors dark-bg selfies."""
    rgb = np.ones((size, size, 3), dtype=np.float32) * 18.0
    yy, xx = np.mgrid[0:size, 0:size]
    cy, cx = size * 0.42, size * 0.5
    r = size * 0.28
    face = ((yy - cy) ** 2 + (xx - cx) ** 2) < r**2
    rgb[face] = (170.0, 140.0, 120.0)
    # darker hair ring
    hair = (((yy - cy) ** 2 + (xx - cx) ** 2) < (r * 1.15) ** 2) & (~face)
    rgb[hair] = (40.0, 35.0, 32.0)
    return rgb


def test_dark_bg_hatch_skips_flat_border():
    rgb = _dark_bg_bright_face(180)
    lum = luminance(rgb)
    hatch = hatch_from_lum(lum, hatch_size=16, jitter=0.0)
    assert hatch, "face midtones should still hatch"
    # Count hatch endpoints that fall in the outer dark border (margin 12%)
    h, w = lum.shape
    mx, my = int(w * 0.12), int(h * 0.12)
    border_hits = 0
    face_hits = 0
    for pts in hatch:
        for x, y in pts:
            if x < mx or y < my or x > w - mx or y > h - my:
                border_hits += 1
            else:
                face_hits += 1
    assert border_hits < face_hits * 0.15, (
        f"too much hatch on dark border: border={border_hits} face={face_hits}"
    )


def test_face_features_produce_interior_edges():
    """Bright face with dark glasses + mouth marks should yield interior paths."""
    size = 200
    rgb = _dark_bg_bright_face(size)
    # glasses rectangle + mouth
    rgb[55:62, 70:130] = (25, 25, 25)
    rgb[55:90, 70:78] = (25, 25, 25)
    rgb[55:90, 122:130] = (25, 25, 25)
    rgb[110:114, 85:115] = (60, 40, 40)
    contours, _ = contours_from_lum(luminance(rgb), simplify=1, jitter=0.0, max_paths=400)
    assert len(contours) >= 3
    # At least one path should land in the face interior band (not only outer ring)
    interior = 0
    for c in contours:
        for x, y in c:
            if 50 < x < 150 and 50 < y < 140:
                interior += 1
                break
    assert interior >= 2, f"expected interior face edges, got interior_hits={interior}"


def test_linework_skips_region_spikes_by_default():
    from botdraw.core.models import PaletteSet, Pen, StyleParams, QualityPreset
    from botdraw.portrait.models import PortraitVector, RegionPoly, CropRect
    from botdraw.portrait.restyle import restyle_linework

    # Spiky page-spanning region that must be rejected
    spike = [(0.0, 0.0), (200.0, 0.0), (5.0, 280.0), (0.0, 0.0)]
    edge = [[(40.0, 40.0), (80.0, 40.0), (80.0, 90.0)]]
    hatch = [[(50.0, 60.0), (90.0, 60.0)]]
    rgb = np.ones((32, 32, 3), dtype=np.float32) * 128
    lum = np.ones((32, 32), dtype=np.float32) * 128
    pv = PortraitVector(
        width_px=32,
        height_px=32,
        rgb=rgb,
        lum=lum,
        ink_target=np.clip(1.0 - lum / 255.0, 0, 1).astype(np.float32),
        edge_map=np.zeros((32, 32), dtype=np.float32),
        page_w_mm=210.0,
        page_h_mm=297.0,
        crop=CropRect(),
        regions=[
            RegionPoly(id="r0", points_mm=spike, mean_rgb=(80, 40, 40), area=999),
        ],
        edge_polylines_mm=edge,
        hatch_polylines_mm=hatch,
        pen_map={"edge": "black", "hatch": "navy", "r0": "crimson"},
    )
    palette = PaletteSet(
        id="t",
        name="t",
        pens=[
            Pen(id="black", name="Black", color_hex="#111111"),
            Pen(id="navy", name="Navy", color_hex="#1e3a5f"),
            Pen(id="crimson", name="Crimson", color_hex="#9b1b30"),
        ],
    )
    layered = restyle_linework(pv, palette, StyleParams(quality=QualityPreset.BOOTH_BALANCED, seed=1))
    pens = {p.pen_id for pas in layered.passes for p in pas.polylines}
    assert "crimson" not in pens
    assert "black" in pens


def test_skeleton_chains_longer_than_raw_mask_walk():
    """Thinning should yield fewer, longer centerline strokes on a thick bar."""
    rgb = np.ones((120, 160, 3), dtype=np.float32) * 240
    rgb[40:80, 20:140] = 20  # thick horizontal bar
    from botdraw.portrait.linedraw_edges import _zhang_suen_thin, edge_bitmap, autocontrast_lum

    lum = autocontrast_lum(luminance(rgb))
    mask = edge_bitmap(lum.astype(np.float32), low=40, high=90)
    skel = _zhang_suen_thin(mask, max_iter=12)
    assert int(skel.sum()) < int(mask.sum()), "skeleton should be thinner than edge band"
    contours, _ = contours_from_lum(luminance(rgb), simplify=1, jitter=0.0, max_paths=200)
    assert contours
    lengths = []
    for c in contours:
        t = 0.0
        for i in range(1, len(c)):
            t += ((c[i][0] - c[i - 1][0]) ** 2 + (c[i][1] - c[i - 1][1]) ** 2) ** 0.5
        lengths.append(t)
    assert max(lengths) > 40.0


def test_merge_bidirectional_joins_reversed_fragments():
    from botdraw.portrait.linedraw_edges import _merge_bidirectional

    a = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    # Oriented away from a's end; reverse join should still connect
    b = [(40.0, 0.0), (30.0, 0.0), (22.0, 0.0)]
    merged = _merge_bidirectional([a, b], dist_thresh=5.0)
    assert len(merged) == 1
    assert len(merged[0]) >= 5


def test_curve_tone_skips_dark_wall():
    from botdraw.portrait.linedraw_edges import curve_tone_from_lum

    rgb = _dark_bg_bright_face(160)
    curves = curve_tone_from_lum(luminance(rgb), cell=14, jitter=0.0, max_paths=800)
    assert curves
    h, w = 160, 160
    mx, my = int(w * 0.12), int(h * 0.12)
    border = face = 0
    for pts in curves:
        for x, y in pts:
            if x < mx or y < my or x > w - mx or y > h - my:
                border += 1
            else:
                face += 1
    assert border < face * 0.2


def test_hatch_off_empty():
    lum = luminance(synthetic_portrait(96).astype(np.float32))
    assert hatch_from_lum(lum, hatch_size=0) == []
    _, hatch, _ = linedraw_edges_and_hatch(
        lum, page_w=100, page_h=150, hatch_size=0, contour_simplify=2, jitter=0
    )
    assert hatch == []


def test_vertical_bar_contour_extent():
    rgb = np.ones((120, 80, 3), dtype=np.float32) * 240
    rgb[20:100, 35:45] = 30
    contours, _ = contours_from_lum(luminance(rgb), simplify=1, jitter=0.0)
    assert contours
    max_dy = max((max(p[1] for p in c) - min(p[1] for p in c)) for c in contours)
    assert max_dy > 20.0


def test_ingest_dark_bg_hatch_meta():
    # This targets the classic linedraw extractor specifically, so pin
    # line_source rather than relying on neural weights being absent.
    pv = ingest_portrait(
        image_array=_dark_bg_bright_face(160),
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        paper="A5",
        auto_frame=False,
        hatch_size=18,
        linedraw_jitter=0.04,
        line_source="classic",
    )
    assert pv.meta.get("edge_extractor") == "linedraw"
    assert pv.meta.get("linedraw_jitter") == 0.04
    assert len(pv.edge_polylines_mm) >= 1
    assert len(pv.hatch_polylines_mm) >= 1


def test_api_hatch_off():
    r = client.post(
        "/api/portrait/ingest",
        json={
            "image_mode": "photo",
            "quality": "booth-fast",
            "paper": "A5",
            "force_reingest": True,
            "include_preview_png": False,
            "hatch_size": 0,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["hatch_count"] == 0
    assert data["meta"]["hatch_size"] == 0
    assert data["edge_count"] >= 1
