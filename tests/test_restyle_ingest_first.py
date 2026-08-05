"""Fill styles prefer ingest tone_codes over classic ink_target."""
from __future__ import annotations

import numpy as np

from botdraw.core.models import QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.portrait.models import PortraitVector
from botdraw.portrait.pens import assign_pens
from botdraw.portrait.restyle import (
    _fill_budget,
    _shade_density_map,
    restyle_hatch,
    restyle_linework,
    restyle_squiggle,
    restyle_stipple,
    restyle_tsp,
)


def _stub_pv(*, neural: bool = True) -> PortraitVector:
    """Portrait with tone_codes on the left and misleading ink_target on the right."""
    h, w = 64, 64
    rgb = np.full((h, w, 3), 200.0, dtype=np.float32)
    lum = np.full((h, w), 200.0, dtype=np.float32)
    # Classic ink says the RIGHT half is dark — styles must ignore this when tone_codes exist
    ink = np.zeros((h, w), dtype=np.float32)
    ink[:, w // 2 :] = 0.9
    edge = np.zeros((h, w), dtype=np.float32)
    # Tone codes: LEFT half shaded, right empty (opposite of ink_target)
    gh, gw = 16, 16
    codes = np.zeros((gh, gw), dtype=np.uint8)
    codes[:, : gw // 2] = 3
    codes[gh // 3 : 2 * gh // 3, gw // 8 : 3 * gw // 8] = 4
    hatch = [[(10.0, float(y)), (40.0, float(y))] for y in range(20, 80, 4)]
    edges = [[(5.0, 10.0), (5.0, 90.0)], [(50.0, 10.0), (55.0, 40.0)]]
    pv = PortraitVector(
        width_px=w,
        height_px=h,
        page_w_mm=100.0,
        page_h_mm=100.0,
        rgb=rgb,
        lum=lum,
        ink_target=ink,
        edge_map=edge,
        edge_polylines_mm=edges,
        hatch_polylines_mm=hatch,
        tone_codes=codes,
        tone_grid=codes.astype(np.float32) / 4.0,
        tone_cell_mm=100.0 / gw,
        meta={
            "line_source": "neural" if neural else "classic",
            "tone_grid": {"cell_px": float(w / gw)},
            "linedraw_jitter": 0.0,
        },
    )
    return pv


def test_shade_density_map_prefers_tone_codes():
    pv = _stub_pv()
    dens, src = _shade_density_map(pv)
    assert src == "tone_codes"
    # Left half of upsampled map should be darker (higher density) than right
    assert float(dens[:, :32].mean()) > float(dens[:, 32:].mean()) * 2


def test_shade_density_map_falls_back_to_ink_target():
    pv = _stub_pv()
    pv.tone_codes = None
    dens, src = _shade_density_map(pv)
    assert src == "ink_target"
    assert float(dens[:, 32:].mean()) > float(dens[:, :32].mean())


def test_squiggle_uses_tone_codes_not_ink_target():
    palette = load_palette("default-6")
    pv = assign_pens(_stub_pv(), palette)
    layered = restyle_squiggle(pv, palette, StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=1.0))
    assert "tone_codes" in (layered.meta.get("vector_source") or "")
    # Squiggle points should concentrate on the left (tone_codes side)
    xs = []
    for pas in layered.passes:
        if pas.id.startswith("sq"):
            for poly in pas.polylines:
                xs.extend(p[0] for p in poly.points)
    assert xs, "expected squiggle strokes"
    assert sum(1 for x in xs if x < 50) > sum(1 for x in xs if x >= 50)


def test_stipple_uses_tone_codes_not_ink_target():
    palette = load_palette("default-6")
    pv = assign_pens(_stub_pv(), palette)
    layered = restyle_stipple(pv, palette, StyleParams(seed=2, quality=QualityPreset.BOOTH_FAST, density=1.0))
    assert "tone_codes" in (layered.meta.get("vector_source") or "")
    xs = []
    for pas in layered.passes:
        if pas.id.startswith("stipple"):
            for poly in pas.polylines:
                xs.append(sum(p[0] for p in poly.points) / len(poly.points))
    assert xs, "expected stipple dots"
    assert sum(1 for x in xs if x < 50) > sum(1 for x in xs if x >= 50)


def test_tsp_inherits_tone_codes_sampling():
    palette = load_palette("default-6")
    pv = assign_pens(_stub_pv(), palette)
    layered = restyle_tsp(pv, palette, StyleParams(seed=3, quality=QualityPreset.BOOTH_FAST, density=1.0))
    assert "tone_codes" in (layered.meta.get("vector_source") or "")


def test_hatch_prefers_ingest_polylines():
    palette = load_palette("default-6")
    pv = assign_pens(_stub_pv(), palette)
    layered = restyle_hatch(pv, palette, StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=1.0))
    assert layered.meta.get("vector_source") in ("mesh_walks", "ingest_hatch")


def test_neural_fill_budget_is_relaxed():
    params = StyleParams(seed=0, quality=QualityPreset.BOOTH_BALANCED, density=1.0)
    neural = _stub_pv(neural=True)
    classic = _stub_pv(neural=False)
    # With 100 edges used, neural gets the remainder; classic is capped at ~limit/3
    n_budget = _fill_budget(neural, params, edges_used=100)
    c_budget = _fill_budget(classic, params, edges_used=100)
    assert n_budget > c_budget
    assert n_budget == 2500 - 100  # booth-balanced max_paths


def test_linework_neural_uses_relaxed_hatch_budget():
    palette = load_palette("default-6")
    pv = assign_pens(_stub_pv(neural=True), palette)
    # Flood hatch so classic cap would truncate
    pv.hatch_polylines_mm = [[(float(i), 10.0), (float(i), 20.0)] for i in range(2000)]
    layered = restyle_linework(
        pv, palette, StyleParams(seed=1, quality=QualityPreset.BOOTH_BALANCED, density=1.0)
    )
    hatch_n = sum(len(p.polylines) for p in layered.passes if "midtone" in p.id or "Midtone" in p.name)
    # Neural should keep far more than the classic limit//3 (~833)
    assert hatch_n > 900
