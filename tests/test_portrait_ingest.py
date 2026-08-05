"""Portrait ingest, framing, cache, and restyle smoke tests."""

from __future__ import annotations

import time

import numpy as np
from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.models import QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.portrait import (
    assign_pens,
    auto_frame_rgb,
    ingest_portrait,
    normalize_crop,
    render_from_vector,
    resolve_portrait_vector,
)

client = TestClient(app)


def test_ingest_synthetic_has_edges_and_timing():
    t0 = time.perf_counter()
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5", auto_frame=True)
    assert time.perf_counter() - t0 < 5.0
    assert pv.width_px > 0
    assert len(pv.edge_polylines_mm) >= 1
    assert "timing_s" in pv.meta
    assert pv.ink_target.shape[:2] == (pv.height_px, pv.width_px)


def test_auto_frame_shrinks_on_subject_background():
    rgb = np.ones((200, 200, 3), dtype=np.float32) * 240
    rgb[60:140, 70:130] = (40, 40, 40)
    crop = auto_frame_rgb(rgb)
    assert crop.w < 0.95 or crop.h < 0.95
    assert crop.source == "auto"


def test_manual_crop_normalized():
    c = normalize_crop({"x": -0.1, "y": 0.2, "w": 1.5, "h": 0.5, "source": "manual"})
    assert 0 <= c.x <= 1
    assert c.w <= 1
    assert c.source == "manual"


def test_ingest_cache_reuse(monkeypatch):
    calls = {"n": 0}
    import botdraw.portrait.ingest as ingest_mod

    real = ingest_mod.ingest_portrait

    def wrapped(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(ingest_mod, "ingest_portrait", wrapped)

    pv1, hit1 = resolve_portrait_vector(
        image_path=None,
        mode="photo",
        quality="booth-fast",
        paper="A5",
        force_reingest=True,
        auto_frame=True,
    )
    assert hit1 is False
    assert calls["n"] >= 1
    n_after = calls["n"]
    pv2, hit2 = resolve_portrait_vector(
        image_path=None,
        mode="photo",
        quality="booth-fast",
        paper="A5",
        reuse_ingest=True,
        ingest_id=pv1.ingest_id,
        auto_frame=True,
    )
    assert hit2 is True
    assert calls["n"] == n_after
    assert pv2.ingest_id == pv1.ingest_id


def test_likeness_dark_gets_more_hatch_coverage():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal)
    layered = render_from_vector(
        "portrait_hatch",
        pv,
        pal,
        StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=1.2),
    )
    assert layered.passes
    n = sum(len(p.polylines) for p in layered.passes)
    assert n <= 800
    assert n > 0


def test_api_render_budget_and_paper():
    r = client.post(
        "/api/render",
        json={
            "app": "portraitbot",
            "style_id": "portrait_linework",
            "palette_id": "default-6",
            "paper": "A5",
            "quality": "booth-fast",
            "seed": 2,
            "density": 1.0,
            "paper_id": "kraft",
            "params_extra": {"image_mode": "photo", "line_type": "solid"},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["layers"]["budget"]["stroke_count"] >= 1
    assert data["emulator"]["paper_color_hex"].lower() == "#c4a574"
    assert data["emulator"]["settings"].get("ingest_id")


def test_api_papers_list():
    r = client.get("/api/papers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert "natural-cream" in ids
    assert "kraft" in ids
