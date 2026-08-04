"""Portrait mesh IR + interface shade walks."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import QualityPreset
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.portrait_mesh import (
    build_portrait_mesh,
    default_mesh_cell_px,
    prune_edges_with_mesh,
    strokes_from_mesh_walks,
)
from botdraw.styles.image_utils import luminance


def _dark_bg_bright_face(size: int = 180) -> np.ndarray:
    rgb = np.ones((size, size, 3), dtype=np.float32) * 18.0
    yy, xx = np.mgrid[0:size, 0:size]
    cy, cx = size * 0.42, size * 0.5
    r = size * 0.28
    face = ((yy - cy) ** 2 + (xx - cx) ** 2) < r**2
    rgb[face] = (170.0, 140.0, 120.0)
    cheek = ((yy - (cy + 8)) ** 2 + (xx - (cx - 18)) ** 2) < (r * 0.22) ** 2
    rgb[cheek & face] = (130.0, 105.0, 95.0)
    return rgb


def test_default_mesh_cell_px():
    assert default_mesh_cell_px("studio-hq") == 5
    assert default_mesh_cell_px("booth-balanced") == 6
    assert default_mesh_cell_px("booth-fast") == 8


def test_mesh_builds_links_and_walks_longer_than_cell():
    rgb = _dark_bg_bright_face(200)
    lum = luminance(rgb).astype(np.float32)
    ink = np.clip(1.0 - lum / 255.0, 0, 1).astype(np.float32)
    mesh = build_portrait_mesh(
        lum, ink, cell_px=5, edge_map=None, page_w_mm=100.0, page_h_mm=100.0, max_code=4
    )
    assert mesh["link_h"].shape[0] == mesh["tone_codes"].shape[0]
    assert int(mesh["link_h"].sum()) >= 1
    strokes = strokes_from_mesh_walks(
        mesh, img_w=200, img_h=200, page_w=100, page_h=100, style="hatch", jitter=0.0, max_paths=500
    )
    assert strokes
    # At least one stroke spans > 1.5 cells (joined run)
    cell_mm = mesh["tone_cell_mm"]
    long_runs = 0
    for pts in strokes:
        span = abs(pts[-1][0] - pts[0][0]) + abs(pts[-1][1] - pts[0][1])
        if span > cell_mm * 1.5:
            long_runs += 1
    assert long_runs >= 1, "expected horizontal interface joins"


def test_mesh_prune_drops_weak_outside_islands():
    mesh = {
        "tone_cell_px": 5.0,
        "mesh_edge": np.zeros((10, 10), dtype=np.float32),
        "edge_degree": np.zeros((10, 10), dtype=np.uint8),
        "mesh_face": np.zeros((10, 10), dtype=np.uint8),
        "img_shape": (50, 50),
    }
    # Face band with edge support
    mesh["mesh_face"][3:7, 3:7] = 1
    mesh["mesh_edge"][3:7, 3:7] = 0.5
    mesh["edge_degree"][3:7, 3:7] = 2
    face_stroke = [(20.0, 20.0), (22.0, 20.0), (24.0, 21.0), (26.0, 22.0)]
    # Short weak outside island
    island = [(2.0, 2.0), (4.0, 2.0), (6.0, 3.0)]
    kept = prune_edges_with_mesh([face_stroke, island], mesh)
    assert any(abs(c[0][0] - 20.0) < 1 for c in kept)
    assert not any(abs(c[0][0] - 2.0) < 1 for c in kept)


def test_ingest_uses_mesh_walks_and_finer_default():
    rgb = _dark_bg_bright_face(160)
    rgb[40:46, 55:105] = 20
    pv = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.STUDIO_HQ,
        paper="A5",
        auto_frame=False,
        ensemble=False,
    )
    assert pv.meta.get("hatch_size") == 5
    assert (pv.meta or {}).get("tone_grid", {}).get("shade_source") == "mesh_walks"
    assert pv.tone_codes is not None
    assert pv.mesh_edge is not None
    assert len(pv.hatch_polylines_mm) >= 1
