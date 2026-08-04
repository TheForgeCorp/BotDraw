"""Linedraw-style ingest edges + hatch tests."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from botdraw.api.main import app
from botdraw.core.models import QualityPreset
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.linedraw_edges import contours_from_lum, hatch_from_lum, linedraw_edges_and_hatch
from botdraw.styles.image_utils import luminance, synthetic_portrait

client = TestClient(app)


def test_dual_axis_vertical_bar_contour():
    rgb = np.ones((120, 80, 3), dtype=np.float32) * 240
    rgb[20:100, 35:45] = 30
    lum = luminance(rgb)
    contours, _ = contours_from_lum(lum, simplify=1, jitter=0.0)
    assert contours, "expected contours"
    max_dy = 0.0
    for pts in contours:
        ys = [p[1] for p in pts]
        max_dy = max(max_dy, max(ys) - min(ys) if ys else 0.0)
    assert max_dy > 20.0, f"expected vertical extent, got {max_dy}"


def test_hatch_size_zero_empty():
    lum = luminance(synthetic_portrait(96).astype(np.float32))
    assert hatch_from_lum(lum, hatch_size=0) == []
    edges, hatch, _ = linedraw_edges_and_hatch(
        lum, page_w=100, page_h=150, hatch_size=0, contour_simplify=2, jitter=0
    )
    assert edges
    assert hatch == []


def test_ingest_uses_linedraw_and_hatch_off():
    rgb = synthetic_portrait(128).astype(np.float32)
    pv = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        hatch_size=0,
        contour_simplify=2,
        linedraw_jitter=0.0,
    )
    assert pv.meta.get("edge_extractor") == "linedraw"
    assert pv.meta.get("hatch_size") == 0
    assert pv.hatch_polylines_mm == []
    assert len(pv.edge_polylines_mm) >= 1


def test_ingest_with_hatch_produces_strokes():
    rgb = synthetic_portrait(160).astype(np.float32)
    pv = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        paper="A5",
        auto_frame=False,
        hatch_size=16,
        contour_simplify=2,
        linedraw_jitter=0.05,
    )
    assert len(pv.hatch_polylines_mm) >= 1
    assert pv.meta.get("hatch_count") == len(pv.hatch_polylines_mm)


def test_api_accepts_linedraw_knobs():
    r = client.post(
        "/api/portrait/ingest",
        json={
            "image_mode": "photo",
            "quality": "booth-fast",
            "paper": "A5",
            "force_reingest": True,
            "include_preview_png": False,
            "contour_simplify": 2,
            "hatch_size": 0,
            "linedraw_jitter": 0.0,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["contour_simplify"] == 2
    assert data["meta"]["hatch_size"] == 0
    assert data["hatch_count"] == 0
    assert "hatch_polylines_mm" in data
    assert data["edge_count"] >= 1


def test_api_upload_hatch_knob(tmp_path):
    p = tmp_path / "face.png"
    Image.fromarray(synthetic_portrait(96).astype(np.uint8)).save(p)
    with p.open("rb") as fh:
        r = client.post(
            "/api/portrait/ingest/upload",
            data={
                "image_mode": "photo",
                "quality": "booth-fast",
                "paper": "A5",
                "force_reingest": "true",
                "contour_simplify": "2",
                "hatch_size": "16",
                "linedraw_jitter": "0.1",
            },
            files={"file": ("face.png", fh, "image/png")},
        )
    assert r.status_code == 200
    assert r.json()["hatch_count"] >= 1
