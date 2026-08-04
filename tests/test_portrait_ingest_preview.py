"""Ingest preview API + connected contour smoke tests."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from botdraw.api.main import app
from botdraw.core.models import QualityPreset
from botdraw.portrait.ingest import _edge_polylines, ingest_portrait
from botdraw.portrait.preview import portrait_vector_preview_dict, portrait_vector_raw_svg
from botdraw.styles.image_utils import map_to_page

client = TestClient(app)


def test_preview_dict_and_raw_svg():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5", auto_frame=True)
    d = portrait_vector_preview_dict(pv, include_preview_png=True)
    assert d["ingest_id"]
    assert "edge_polylines_mm" in d
    assert d["edge_count"] == len(pv.edge_polylines_mm)
    assert d.get("preview_png_b64")
    svg = portrait_vector_raw_svg(pv)
    assert "<svg" in svg
    assert 'id="edges"' in svg
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
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ingest_id"]
    assert isinstance(data["edge_polylines_mm"], list)
    assert data["edge_count"] >= 1
    assert data["page_mm"][0] > 0

    g = client.get(f"/api/portrait/ingest/{data['ingest_id']}")
    assert g.status_code == 200
    assert g.json()["ingest_id"] == data["ingest_id"]

    svg = client.get(f"/api/portrait/ingest/{data['ingest_id']}/svg")
    assert svg.status_code == 200
    assert "image/svg+xml" in svg.headers.get("content-type", "")
    assert b"<svg" in svg.content


def test_vertical_bar_yields_non_horizontal_edge():
    """Connected contours must capture vertical structure (not scanlines only)."""
    # Tall dark rectangle on light ground
    rgb = np.ones((120, 80, 3), dtype=np.float32) * 240
    rgb[20:100, 35:45] = 30
    from PIL import ImageFilter

    g = Image.fromarray(np.clip(0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2], 0, 255).astype(np.uint8), mode="L")
    edge_map = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    polys = _edge_polylines(edge_map, step=2, max_paths=200, page_w=100.0, page_h=150.0)
    assert polys, "expected some edge polylines"
    max_dy = 0.0
    for pts in polys:
        ys = [p[1] for p in pts]
        max_dy = max(max_dy, max(ys) - min(ys) if ys else 0.0)
    assert max_dy > 2.0, f"expected vertical extent in contours, got max_dy={max_dy}"


def test_api_ingest_upload(tmp_path):
    from botdraw.styles.image_utils import synthetic_portrait

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
            },
            files={"file": ("face.png", fh, "image/png")},
        )
    assert r.status_code == 200
    assert r.json()["edge_count"] >= 1
