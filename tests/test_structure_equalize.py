"""Structure gap equalize — parallel-H closers for missing band verticals."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from botdraw.core.models import QualityPreset
from botdraw.portrait import ingest_portrait
from botdraw.portrait.gold import ensure_gold_fixtures, load_manifest, run_gold_case
from botdraw.portrait.linedraw_edges import (
    equalize_parallel_gaps,
    refine_edge_polylines,
)
from botdraw.styles.image_utils import luminance


def _banded_body(size: int = 320) -> np.ndarray:
    """Colored body with a flush white horizontal band (mug-like)."""
    img = Image.new("RGB", (size, size), (248, 246, 240))
    d = ImageDraw.Draw(img)
    d.rectangle(
        [size * 0.25, size * 0.20, size * 0.75, size * 0.85],
        fill=(210, 85, 70),
        outline=(35, 35, 35),
        width=3,
    )
    d.rectangle([size * 0.25, size * 0.48, size * 0.75, size * 0.58], fill=(255, 255, 255))
    return np.asarray(img, dtype=np.float32)


def _band_sides(edges_mm, page_w: float, page_h: float) -> tuple[int, int]:
    """Count roughly vertical strokes that span the mid band (left vs right)."""
    y0, y1 = page_h * 0.42, page_h * 0.65
    left = right = 0
    mid = page_w * 0.5
    for pts in edges_mm:
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        height = maxy - miny
        width = maxx - minx
        if height < (y1 - y0) * 0.3:
            continue
        if width > max(2.0, height * 0.7):
            continue
        if maxy < y0 or miny > y1:
            continue
        mx = 0.5 * (minx + maxx)
        if mx < mid:
            left += 1
        else:
            right += 1
    return left, right


def test_equalize_parallel_gaps_adds_vertical_closers():
    top = [(40.0, 50.0), (120.0, 51.0), (200.0, 50.0)]
    bot = [(42.0, 90.0), (118.0, 91.0), (198.0, 90.0)]
    noise = [(10.0, 10.0), (12.0, 40.0), (11.0, 70.0)]
    out, n = equalize_parallel_gaps([top, bot, noise], face=None)
    assert n >= 2
    left = right = 0
    for c in out:
        if len(c) != 2:
            continue
        (x0, y0), (x1, y1) = c
        if abs(x0 - x1) > abs(y0 - y1) * 0.55:
            continue
        if abs(y0 - y1) < 20:
            continue
        mx = 0.5 * (x0 + x1)
        if mx < 100:
            left += 1
        else:
            right += 1
    assert left >= 1 and right >= 1


def test_equalize_skips_face_local_horizontal_pairs():
    h, w = 120, 120
    face = np.zeros((h, w), dtype=bool)
    face[30:90, 30:90] = True
    top = [(40.0, 45.0), (80.0, 46.0)]
    bot = [(41.0, 70.0), (79.0, 71.0)]
    out, n = equalize_parallel_gaps([top, bot], face=face)
    assert n == 0
    assert len(out) == 2


def test_refine_equalizes_synthetic_band_rectangle():
    rgb = _banded_body(320)
    lum = luminance(rgb)
    y0, y1 = 320 * 0.48, 320 * 0.58
    x0, x1 = 320 * 0.25, 320 * 0.75
    contours = [
        [(x0, y0), (x1, y0)],
        [(x0, y1), (x1, y1)],
        [(x0, 320 * 0.20), (x0, 320 * 0.85)],
    ]
    out = refine_edge_polylines(contours, lum, max_paths=50)
    assert getattr(refine_edge_polylines, "last_equalize_added", 0) >= 1
    verts = 0
    for c in out:
        if len(c) < 2:
            continue
        xs = [p[0] for p in c]
        ys = [p[1] for p in c]
        if (max(ys) - min(ys)) >= 0.5 * (y1 - y0) and (max(xs) - min(xs)) <= (y1 - y0):
            verts += 1
    assert verts >= 1


def test_gold_mug_has_band_side_verticals(tmp_path):
    root = tmp_path / "gold"
    ensure_gold_fixtures(root=root, force=True)
    case = next(c for c in load_manifest(root) if c.id == "object-mug")
    result = run_gold_case(case, root=root)
    assert result.passed

    pv = ingest_portrait(
        image_path=root / case.file,
        mode="photo",
        quality=QualityPreset.BOOTH_BALANCED,
        paper="A5",
        auto_frame=True,
        hatch_size=0,
        line_source="classic",
        scan_mode="edges",
        ensemble=False,
    )
    left, right = _band_sides(pv.edge_polylines_mm, pv.page_w_mm, pv.page_h_mm)
    assert left >= 1, f"missing left band vertical (L={left} R={right})"
    assert right >= 1, f"missing right band vertical (L={left} R={right})"
    assert (pv.meta or {}).get("edge_equalize", {}).get("added", 0) >= 1


def test_gold_people_still_pass(tmp_path):
    root = tmp_path / "gold"
    ensure_gold_fixtures(root=root, force=True)
    for case in load_manifest(root):
        if case.category != "people":
            continue
        result = run_gold_case(case, root=root)
        assert result.passed, (case.id, [c for c in result.checks if not c.passed])
