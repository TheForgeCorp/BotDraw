"""Intensity tone grid + edge prep QA."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import QualityPreset
from botdraw.portrait.cache import load_portrait_vector, save_portrait_vector
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.linedraw_edges import contours_from_lum, prepare_luma_for_edges
from botdraw.portrait.tone_grid import build_tone_grid, strokes_from_tone_grid, tone_codes_heatmap_rgb
from botdraw.styles.image_utils import luminance


def _dark_bg_bright_face(size: int = 180) -> np.ndarray:
    rgb = np.ones((size, size, 3), dtype=np.float32) * 18.0
    yy, xx = np.mgrid[0:size, 0:size]
    cy, cx = size * 0.42, size * 0.5
    r = size * 0.28
    face = ((yy - cy) ** 2 + (xx - cx) ** 2) < r**2
    rgb[face] = (170.0, 140.0, 120.0)
    # Midtone cheek shade (slightly darker patch inside face)
    cheek = ((yy - (cy + 8)) ** 2 + (xx - (cx - 18)) ** 2) < (r * 0.22) ** 2
    rgb[cheek & face] = (130.0, 105.0, 95.0)
    hair = (((yy - cy) ** 2 + (xx - cx) ** 2) < (r * 1.15) ** 2) & (~face)
    rgb[hair] = (40.0, 35.0, 32.0)
    return rgb


def test_prepare_luma_for_edges_keeps_shape_and_range():
    lum = luminance(_dark_bg_bright_face(96))
    out = prepare_luma_for_edges(lum)
    assert out.shape == lum.shape
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 255.0
    # Denoise+lift should change flat JPEG-ish input
    assert float(np.mean(np.abs(out.astype(np.float32) - lum.astype(np.float32)))) > 0.5


def test_tone_grid_cheeks_coded_border_skip():
    rgb = _dark_bg_bright_face(200)
    lum = luminance(rgb).astype(np.float32)
    ink = np.clip(1.0 - lum / 255.0, 0, 1).astype(np.float32)
    pack = build_tone_grid(
        lum,
        ink,
        cell_px=14,
        edge_map=None,
        page_w_mm=100.0,
        page_h_mm=100.0,
        max_code=4,
    )
    codes = pack["tone_codes"]
    # Face midtones should get some shade codes
    assert int((codes >= 1).sum()) >= 4, f"expected midtone codes, hist={(codes > 0).sum()}"
    # Outer border cells should stay mostly 0
    h, w = codes.shape
    border = np.ones_like(codes, dtype=bool)
    border[1 : h - 1, 1 : w - 1] = False
    assert int((codes[border] >= 1).sum()) <= max(2, int((codes >= 1).sum()) * 0.2)


def test_strokes_from_tone_grid_hatch_and_scribble():
    codes = np.zeros((8, 8), dtype=np.uint8)
    codes[2:6, 2:6] = 2
    codes[3:5, 3:5] = 4
    hatch = strokes_from_tone_grid(
        codes, cell_px=10, img_w=80, img_h=80, page_w=100, page_h=100, style="hatch", jitter=0.0
    )
    scrib = strokes_from_tone_grid(
        codes, cell_px=10, img_w=80, img_h=80, page_w=100, page_h=100, style="scribble", jitter=0.0
    )
    assert hatch, "hatch style should emit strokes"
    assert scrib, "scribble style should emit strokes"
    heat = tone_codes_heatmap_rgb(codes)
    assert heat.shape == (8, 8, 3)


def test_ingest_persists_tone_grid_and_heatmap():
    rgb = _dark_bg_bright_face(160)
    # glasses for edge structure
    rgb[40:46, 55:105] = 20
    rgb[40:70, 55:62] = 20
    rgb[40:70, 98:105] = 20
    pv = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
    )
    assert pv.tone_codes is not None
    assert pv.tone_grid is not None
    assert pv.tone_cell_mm > 0
    assert (pv.meta or {}).get("edge_prep") == "prepare_luma_for_edges"
    assert (pv.meta or {}).get("tone_grid", {}).get("max_code") == 3  # booth-fast
    assert len(pv.hatch_polylines_mm) >= 1
    # Cache round-trip
    iid = save_portrait_vector(pv)
    loaded = load_portrait_vector(iid)
    assert loaded is not None
    assert loaded.tone_codes is not None
    assert loaded.tone_codes.shape == pv.tone_codes.shape
    from botdraw.portrait.preview import portrait_vector_preview_dict

    d = portrait_vector_preview_dict(pv, include_preview_png=True)
    assert d.get("has_tone_grid")
    assert d.get("tone_heatmap_png_b64")


def test_edge_prep_does_not_collapse_glasses():
    size = 200
    rgb = _dark_bg_bright_face(size)
    rgb[55:62, 70:130] = (25, 25, 25)
    rgb[55:90, 70:78] = (25, 25, 25)
    rgb[55:90, 122:130] = (25, 25, 25)
    contours, _ = contours_from_lum(luminance(rgb), simplify=1, jitter=0.0, max_paths=400, prepare=True)
    assert len(contours) >= 3
    interior = 0
    for c in contours:
        for x, y in c:
            if 50 < x < 150 and 50 < y < 140:
                interior += 1
                break
    assert interior >= 2
