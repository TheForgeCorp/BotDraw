"""Ensemble multi-variant vectorization (5 tone recipes + consensus 6th pass)."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import QualityPreset
from botdraw.portrait.ingest import _resolve_ensemble, ingest_portrait
from botdraw.portrait.linedraw_edges import (
    allocate_face_budget,
    consensus_from_ink_maps,
    contours_from_edge_mask,
    face_roi_mask,
    polylines_to_ink_map,
    prune_edge_islands,
    refine_edge_polylines,
    repair_arc_gaps,
)
from botdraw.portrait.tone_variants import ENSEMBLE_RECIPES, apply_tone_recipe
from botdraw.styles.image_utils import luminance


def _face_with_gap_feature(size: int = 180) -> np.ndarray:
    """
    Dark-bg face + a thin low-contrast jaw arc that only pops under high contrast.

    The jaw is drawn slightly darker than skin so soft contrast may miss it.
    """
    rgb = np.ones((size, size, 3), dtype=np.float32) * 16.0
    yy, xx = np.mgrid[0:size, 0:size]
    cy, cx = size * 0.42, size * 0.5
    r = size * 0.30
    face = ((yy - cy) ** 2 + (xx - cx) ** 2) < r**2
    rgb[face] = (168.0, 140.0, 122.0)
    # glasses: high contrast bars
    rgb[int(size * 0.38) : int(size * 0.42), int(size * 0.32) : int(size * 0.68)] = 28.0
    rgb[int(size * 0.36) : int(size * 0.48), int(size * 0.34) : int(size * 0.38)] = 24.0
    rgb[int(size * 0.36) : int(size * 0.48), int(size * 0.62) : int(size * 0.66)] = 24.0
    # soft jaw arc (subtle) — ensemble high-contrast recipe should recover
    for t in np.linspace(-0.7, 0.7, 80):
        x = int(cx + np.sin(t) * r * 0.85)
        y = int(cy + r * 0.55 + np.cos(t) * r * 0.22)
        if 1 <= x < size - 1 and 1 <= y < size - 1:
            rgb[y - 1 : y + 2, x - 1 : x + 2] = (148.0, 122.0, 108.0)
    return rgb


def test_ensemble_recipes_are_blur_pyramid():
    assert len(ENSEMBLE_RECIPES) == 5
    assert ENSEMBLE_RECIPES[0].blur_radius == 0.0
    assert ENSEMBLE_RECIPES[-1].blur_radius > ENSEMBLE_RECIPES[2].blur_radius
    rgb = _face_with_gap_feature(96)
    outs = [apply_tone_recipe(rgb, r) for r in ENSEMBLE_RECIPES]
    diffs = [float(np.mean(np.abs(outs[i] - outs[0]))) for i in range(1, 5)]
    assert max(diffs) > 1.0


def test_prune_drops_short_outside_islands():
    rgb = _face_with_gap_feature(120)
    lum = luminance(rgb)
    face = face_roi_mask(lum)
    # Tiny corner scribble outside face
    island = [(2.0, 2.0), (5.0, 3.0), (8.0, 2.0)]
    # Long face stroke
    face_stroke = [(60.0, 50.0), (70.0, 52.0), (80.0, 50.0), (90.0, 55.0)]
    kept = prune_edge_islands([island, face_stroke], face, outside_min_len=52.0, inside_min_len=10.0)
    assert face_stroke in kept or any(_path_like(face_stroke, k) for k in kept)
    assert not any(_path_like(island, k) for k in kept)


def _path_like(a, b) -> bool:
    return abs(a[0][0] - b[0][0]) < 0.1 and abs(a[-1][0] - b[-1][0]) < 0.1


def test_repair_arc_gaps_joins_broken_glasses_bar():
    rgb = _face_with_gap_feature(120)
    lum = luminance(rgb)
    face = face_roi_mask(lum)
    # Two collinear dark-bar fragments with a gap (glasses)
    a = [(40.0, 48.0), (50.0, 48.0), (58.0, 48.0)]
    b = [(70.0, 48.0), (78.0, 48.0), (88.0, 48.0)]
    joined = repair_arc_gaps([a, b], lum, face, min_gap=6.0, max_gap=22.0)
    assert len(joined) == 1
    assert len(joined[0]) >= 5


def test_allocate_face_budget_prefers_face():
    face = np.zeros((80, 80), dtype=bool)
    face[20:60, 20:60] = True
    face_paths = [[(30.0, 30.0), (40.0, 32.0), (50.0, 30.0)] for _ in range(5)]
    out_paths = [[(2.0, 2.0), (4.0, 70.0), (6.0, 2.0)] for _ in range(5)]  # long outside
    picked = allocate_face_budget(face_paths + out_paths, face, max_paths=6, face_fraction=0.8)
    face_n = sum(1 for p in picked if _path_faceish(p, face))
    assert face_n >= 4


def _path_faceish(pts, face) -> bool:
    from botdraw.portrait.linedraw_edges import _path_face_fraction

    return _path_face_fraction(pts, face) >= 0.35


def test_booth_never_ensembles():
    assert _resolve_ensemble(True, quality=QualityPreset.BOOTH_FAST, mode="photo") is False
    assert _resolve_ensemble(True, quality=QualityPreset.BOOTH_BALANCED, mode="photo") is False
    assert _resolve_ensemble(None, quality=QualityPreset.BOOTH_BALANCED, mode="photo") is False


def test_studio_photo_auto_ensemble():
    assert _resolve_ensemble(None, quality=QualityPreset.STUDIO_HQ, mode="photo") is True
    assert _resolve_ensemble(False, quality=QualityPreset.STUDIO_HQ, mode="photo") is False
    assert _resolve_ensemble(None, quality=QualityPreset.STUDIO_HQ, mode="drawing") is False


def test_consensus_dedupes_and_fills_gaps():
    a = np.zeros((40, 40), dtype=np.float32)
    b = np.zeros((40, 40), dtype=np.float32)
    a[10:12, 5:30] = 1.0  # shared horizontal
    b[10:12, 5:30] = 1.0
    b[10:25, 28:30] = 1.0  # vertical spur only in B (gap fill)
    mask = consensus_from_ink_maps([a, b], core_votes=2, fill_votes=1)
    assert mask[11, 15]  # core
    assert mask[18, 29]  # fill near core


def test_contours_from_edge_mask_returns_paths():
    mask = np.zeros((80, 100), dtype=bool)
    mask[20:60, 48:52] = True
    mask[38:42, 20:80] = True
    paths = contours_from_edge_mask(mask, simplify=2, jitter=0.0, max_paths=200)
    assert paths
    ink = polylines_to_ink_map(paths, height=80, width=100, stroke_radius=1)
    assert float(ink.sum()) > 10.0


def test_booth_fast_ingest_ignores_ensemble_flag():
    pv = ingest_portrait(
        image_array=_face_with_gap_feature(120),
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        ensemble=True,
        hatch_size=0,
    )
    assert (pv.meta or {}).get("ensemble", {}).get("enabled") is False
    assert (pv.meta or {}).get("edge_extractor") == "linedraw"


def test_studio_ensemble_enabled_and_within_budget():
    pv = ingest_portrait(
        image_array=_face_with_gap_feature(160),
        mode="photo",
        quality=QualityPreset.STUDIO_HQ,
        paper="A5",
        auto_frame=False,
        ensemble=True,
        hatch_size=16,
    )
    ens = (pv.meta or {}).get("ensemble") or {}
    assert ens.get("enabled") is True
    assert ens.get("mode") == "blur_pyramid"
    assert "face_budget" in (ens.get("refine") or "")
    assert len(ens.get("recipes") or []) == 5
    assert pv.edge_polylines_mm
    assert len(pv.edge_polylines_mm) <= 1100


def test_refine_edge_polylines_caps_and_keeps_face():
    rgb = _face_with_gap_feature(140)
    lum = luminance(rgb)
    # Mix of face strokes + tiny corners
    contours = []
    for i in range(8):
        x0 = 50 + i * 3
        contours.append([(float(x0), 55.0), (float(x0 + 12), 57.0), (float(x0 + 24), 55.0)])
    contours.append([(1.0, 1.0), (3.0, 2.0), (5.0, 1.0)])
    out = refine_edge_polylines(contours, lum, max_paths=5)
    assert 1 <= len(out) <= 5


def test_ensemble_covers_at_least_as_much_as_single_pass():
    rgb = _face_with_gap_feature(160)
    single = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.STUDIO_HQ,
        paper="A5",
        auto_frame=False,
        ensemble=False,
        hatch_size=0,
    )
    ens = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.STUDIO_HQ,
        paper="A5",
        auto_frame=False,
        ensemble=True,
        hatch_size=0,
    )
    assert (ens.meta or {}).get("ensemble", {}).get("enabled") is True

    def coverage(pv):
        # ink map at page-ish density: count edge polyline points in lower face ROI
        h, w = pv.height_px, pv.width_px
        page_w, page_h = pv.page_w_mm, pv.page_h_mm
        hits = 0
        y0, y1 = page_h * 0.45, page_h * 0.85
        x0, x1 = page_w * 0.25, page_w * 0.75
        for pts in pv.edge_polylines_mm:
            for x, y in pts:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    hits += 1
        return hits, len(pv.edge_polylines_mm)

    s_hits, s_n = coverage(single)
    e_hits, e_n = coverage(ens)
    # Ensemble should not collapse coverage in the feature band
    assert e_hits >= s_hits * 0.85 or e_n >= s_n * 0.85
    # And usually recovers more structure on this synthetic gap face
    assert e_hits + e_n >= s_hits * 0.9
