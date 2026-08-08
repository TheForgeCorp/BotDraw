"""Ingest preview API + contour quality + SVGcode-style knobs."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

from botdraw.api.main import app
from botdraw.core.models import QualityPreset
from botdraw.portrait.ingest import (
    _edge_polylines,
    _parse_svg_paths,
    _posterize_rgb,
    _vtracer_regions,
    ingest_portrait,
)
from botdraw.portrait.preview import portrait_vector_preview_dict, portrait_vector_raw_svg
from botdraw.styles.image_utils import synthetic_portrait

client = TestClient(app)


def test_preview_dict_and_raw_svg():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5", auto_frame=True)
    d = portrait_vector_preview_dict(pv, include_preview_png=True)
    assert d["ingest_id"]
    assert "edge_polylines_mm" in d
    assert d["edge_count"] == len(pv.edge_polylines_mm)
    assert d.get("preview_png_b64")
    assert d["meta"].get("posterize_levels") is not None
    svg = portrait_vector_raw_svg(pv)
    assert "<svg" in svg
    assert 'id="layer-edges"' in svg or 'id="edges"' in svg
    assert len(svg) > 200


def test_api_portrait_ingest_json():
    r = client.post(
        "/api/portrait/ingest",
        json={
            "image_mode": "photo",
            "quality": "booth-fast",
            "paper": "A5",
            "auto_frame": True,
            "force_reingest": True,
            "include_preview_png": True,
            "posterize_levels": 4,
            "filter_speckle": 12,
            "min_path_points": 6,
            "contrast": 1.1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ingest_id"]
    assert isinstance(data["edge_polylines_mm"], list)
    assert data["edge_count"] >= 1
    assert data["page_mm"][0] > 0
    assert data["meta"]["posterize_levels"] == 4
    assert data["meta"]["filter_speckle"] == 12

    g = client.get(f"/api/portrait/ingest/{data['ingest_id']}")
    assert g.status_code == 200
    assert g.json()["ingest_id"] == data["ingest_id"]

    svg = client.get(f"/api/portrait/ingest/{data['ingest_id']}/svg")
    assert svg.status_code == 200
    assert "image/svg+xml" in svg.headers.get("content-type", "")
    assert b"<svg" in svg.content


def test_vertical_bar_yields_non_horizontal_edge():
    """Connected contours must capture vertical structure (not scanlines only)."""
    rgb = np.ones((120, 80, 3), dtype=np.float32) * 240
    rgb[20:100, 35:45] = 30
    g = Image.fromarray(
        np.clip(0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2], 0, 255).astype(np.uint8),
        mode="L",
    )
    edge_map = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    polys = _edge_polylines(edge_map, step=2, max_paths=200, page_w=100.0, page_h=150.0, min_path_points=4)
    assert polys, "expected some edge polylines"
    max_dy = 0.0
    for pts in polys:
        ys = [p[1] for p in pts]
        max_dy = max(max_dy, max(ys) - min(ys) if ys else 0.0)
    assert max_dy > 2.0, f"expected vertical extent in contours, got max_dy={max_dy}"


def test_api_ingest_upload(tmp_path):
    # The synthetic procedural fixture doesn't resemble a real photo well
    # enough for the neural nets to detect a subject, so pin classic —
    # this test targets the upload/preview plumbing, not detector quality.
    p = tmp_path / "face.png"
    Image.fromarray(synthetic_portrait(96).astype(np.uint8)).save(p)
    with p.open("rb") as fh:
        r = client.post(
            "/api/portrait/ingest/upload",
            data={
                "image_mode": "photo",
                "quality": "booth-fast",
                "paper": "A5",
                "auto_frame": "true",
                "force_reingest": "true",
                "posterize_levels": "4",
                "filter_speckle": "10",
                "line_source": "classic",
            },
            files={"file": ("face.png", fh, "image/png")},
        )
    assert r.status_code == 200
    assert r.json()["edge_count"] >= 1


def test_posterize_reduces_unique_colors():
    yy, xx = np.mgrid[0:64, 0:64]
    rgb = np.stack(
        [
            xx.astype(np.float32) * 4.0,
            yy.astype(np.float32) * 4.0,
            ((xx + yy) % 64).astype(np.float32) * 4.0,
        ],
        axis=-1,
    )
    before = len({(int(r), int(g), int(b)) for r, g, b in rgb.reshape(-1, 3)})
    post = _posterize_rgb(rgb, 4)
    after = len({(int(r), int(g), int(b)) for r, g, b in post.reshape(-1, 3)})
    assert before > 20
    assert after < before
    assert after <= 4**3


def test_vtracer_honors_translate_no_travel_jumps():
    """Region paths must apply translate(); drop full-frame background."""
    rgb = synthetic_portrait(192).astype(np.float32)
    # Heavy posterize + speckle for stable region set
    from botdraw.portrait.ingest import _preprocess_array

    rgb = _preprocess_array(rgb, "photo", posterize_levels=5, contrast=1.1)
    regions = _vtracer_regions(
        rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        page_w=210.0,
        page_h=297.0,
        max_regions=40,
        filter_speckle=10,
        min_path_points=5,
        min_area_px=40.0,
    )
    assert regions, "expected regions from synthetic face"
    h, w = rgb.shape[:2]
    img_area = float(w * h)
    assert all(r.area < 0.82 * img_area for r in regions)
    jumps = 0
    for r in regions:
        pts = r.points_mm
        for i in range(1, len(pts)):
            d = ((pts[i][0] - pts[i - 1][0]) ** 2 + (pts[i][1] - pts[i - 1][1]) ** 2) ** 0.5
            if d > 40:
                jumps += 1
    assert jumps == 0, f"unexpected travel jumps in regions: {jumps}"


def test_parse_svg_applies_translate():
    svg = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
<path d="M0,0 L10,0 L10,10 L0,10 Z " fill="#112233" transform="translate(50,40)"/>
</svg>"""
    paths = _parse_svg_paths(svg)
    assert len(paths) == 1
    pts, fill = paths[0]
    assert fill == "#112233"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) >= 49.0 and max(xs) <= 61.0
    assert min(ys) >= 39.0 and max(ys) <= 51.0


def test_higher_speckle_shrinks_or_equals_region_count():
    rgb = synthetic_portrait(160).astype(np.float32)
    low = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        paper="A5",
        auto_frame=False,
        posterize_levels=5,
        filter_speckle=2,
        min_path_points=4,
        contrast=1.0,
    )
    high = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        paper="A5",
        auto_frame=False,
        posterize_levels=5,
        filter_speckle=20,
        min_path_points=4,
        contrast=1.0,
    )
    assert high.meta["region_count"] <= low.meta["region_count"]


def test_min_path_points_filters_short_edges():
    rgb = np.ones((80, 80, 3), dtype=np.float32) * 220
    # sprinkle noise + one long vertical edge
    rng = np.random.default_rng(0)
    noise = rng.random((80, 80)) > 0.97
    rgb[noise] = 10
    rgb[10:70, 40:42] = 10
    loose = ingest_portrait(
        image_array=rgb,
        mode="drawing",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        posterize_levels=2,
        filter_speckle=4,
        min_path_points=3,
        contrast=1.0,
    )
    strict = ingest_portrait(
        image_array=rgb,
        mode="drawing",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        posterize_levels=2,
        filter_speckle=4,
        min_path_points=20,
        contrast=1.0,
    )
    assert strict.meta["edge_count"] <= loose.meta["edge_count"]
