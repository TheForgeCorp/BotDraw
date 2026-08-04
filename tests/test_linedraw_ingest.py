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
    pv = ingest_portrait(
        image_array=_dark_bg_bright_face(160),
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        paper="A5",
        auto_frame=False,
        hatch_size=18,
        linedraw_jitter=0.04,
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
