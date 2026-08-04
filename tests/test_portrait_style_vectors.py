"""Portrait styles consume linedraw ingest vectors."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.pens import assign_pens
from botdraw.portrait.restyle import render_from_vector, restyle_hatch, restyle_linework
from botdraw.styles import ensure_styles_loaded, get_style
from botdraw.styles.image_utils import synthetic_portrait


def _pv_with_hatch():
    rgb = synthetic_portrait(128).astype(np.float32)
    pv = ingest_portrait(
        image_array=rgb,
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        hatch_size=16,
        linedraw_jitter=0.0,
    )
    assert pv.hatch_polylines_mm, "expected ingest hatch for this test"
    palette = load_palette("default-6")
    return assign_pens(pv, palette), palette


def test_linework_uses_ingest_edges_and_hatch():
    ensure_styles_loaded()
    pv, palette = _pv_with_hatch()
    layered = restyle_linework(pv, palette, StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=1.0))
    n = sum(len(p.polylines) for p in layered.passes)
    assert n >= len(pv.edge_polylines_mm)
    assert layered.meta.get("vector_source") == "ingest"


def test_hatch_style_prefers_ingest_hatch():
    ensure_styles_loaded()
    pv, palette = _pv_with_hatch()
    layered = restyle_hatch(pv, palette, StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=1.0))
    assert layered.meta.get("vector_source") == "ingest_hatch"
    n = sum(len(p.polylines) for p in layered.passes)
    assert n >= len(pv.hatch_polylines_mm)


def test_style_engine_render_from_pipeline_vector():
    ensure_styles_loaded()
    pv, palette = _pv_with_hatch()
    eng = get_style("portrait_linework")
    layered = eng.render(
        palette=palette,
        params=StyleParams(
            seed=2,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            extra={"portrait_vector": pv},
        ),
        paper=pv.page_w_mm and __import__("botdraw.core.models", fromlist=["PaperSize"]).PaperSize.A5,
    )
    assert layered.passes
    assert layered.meta.get("ingest_id") == pv.ingest_id or layered.meta.get("portrait_style") == "portrait_linework"


def test_render_from_vector_meta_counts():
    pv, palette = _pv_with_hatch()
    layered = render_from_vector(
        "portrait_hatch",
        pv,
        palette,
        StyleParams(seed=0, quality=QualityPreset.BOOTH_FAST, density=1.0),
    )
    assert layered.meta.get("hatch_count") == len(pv.hatch_polylines_mm)
    assert layered.meta.get("edge_count") == len(pv.edge_polylines_mm)
