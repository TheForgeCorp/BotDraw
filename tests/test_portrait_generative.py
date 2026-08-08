"""Generative portrait ink path — manual provider + mocked APIs (no live calls)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from botdraw.core.models import ArtisticUse, LineProfile, Pen, TipShape
from botdraw.palettes import load_palette
from botdraw.portrait.generative import (
    generate_portrait_ink,
    generative_available,
    generative_unavailable_reason,
    ink_tone_corr,
    raster_to_ink,
)
from botdraw.portrait.ingest import ingest_portrait

FIXTURE = Path(__file__).parent / "fixtures" / "portrait" / "generative" / "line_ink_fixture.png"


@pytest.fixture
def line_ink_path(tmp_path, monkeypatch):
    assert FIXTURE.is_file(), f"missing fixture {FIXTURE}"
    monkeypatch.setenv("BOTDRAW_GENERATIVE_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_GENERATIVE_INK", str(FIXTURE))
    return FIXTURE


def test_pen_schema_tip_shape_and_artistic_use_defaults():
    pen = Pen(id="x", name="X")
    assert pen.profile.tip_shape == TipShape.UNKNOWN
    assert pen.profile.diameter_mm is None
    assert pen.preferred_uses == [ArtisticUse.ANY]


def test_pen_schema_round_trip_optional_fields():
    pen = Pen(
        id="marker1",
        name="Chisel Navy",
        color_hex="#1a2744",
        preferred_uses=[ArtisticUse.SHADE, ArtisticUse.FILL],
        profile=LineProfile(
            width_mm=1.2,
            diameter_mm=2.0,
            tip_shape=TipShape.CHISEL,
        ),
    )
    data = pen.model_dump()
    again = Pen.model_validate(data)
    assert again.profile.tip_shape == TipShape.CHISEL
    assert again.profile.diameter_mm == 2.0
    assert ArtisticUse.SHADE in again.preferred_uses


def test_existing_palette_loads_with_new_pen_fields():
    pal = load_palette("default-6")
    assert len(pal.pens) >= 2
    for pen in pal.pens:
        assert pen.profile.tip_shape == TipShape.UNKNOWN
        assert pen.preferred_uses == [ArtisticUse.ANY]


def test_manual_provider_available(line_ink_path):
    assert generative_available("manual")
    assert generative_unavailable_reason("manual") is None


def test_manual_provider_missing(monkeypatch):
    monkeypatch.setenv("BOTDRAW_GENERATIVE_PROVIDER", "manual")
    monkeypatch.delenv("BOTDRAW_GENERATIVE_INK", raising=False)
    assert not generative_available("manual")
    reason = generative_unavailable_reason("manual")
    assert reason and "BOTDRAW_GENERATIVE_INK" in reason


def test_generate_portrait_ink_manual(line_ink_path):
    rgb = np.full((160, 128, 3), 200, dtype=np.float32)
    pack = generate_portrait_ink(rgb, provider="manual", ink_path=line_ink_path, allow_retry=False)
    assert pack is not None
    ink = pack["ink"]
    assert ink.shape == (160, 128)
    assert float(ink.max()) > 0.5  # has dark strokes
    assert pack["meta"]["provider"] == "manual"
    assert "ink_png_b64" in pack["meta"]
    assert "fidelity" in pack["meta"]


def test_generate_fidelity_retry_keeps_best(monkeypatch):
    """When first attempt scores low, retry once and keep the better corr."""
    rgb = np.full((80, 64, 3), 220, dtype=np.float32)
    photo_ink = np.zeros((80, 64), dtype=np.float32)
    photo_ink[20:60, 16:48] = 1.0
    good = photo_ink.copy()
    bad = 1.0 - photo_ink
    calls = {"n": 0}

    def fake_call(rgb, *, provider, prompt, seed, ink_path=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return bad, {"provider": "manual", "prompt_variant": "first"}
        return good, {"provider": "manual", "prompt_variant": "strict"}

    monkeypatch.setattr(
        "botdraw.portrait.generative._call_provider",
        fake_call,
    )
    pack = generate_portrait_ink(
        rgb,
        provider="manual",
        photo_ink_target=photo_ink,
        tone_corr_min=0.9,  # force retry
        allow_retry=True,
    )
    assert pack is not None
    assert calls["n"] == 2
    assert pack["meta"]["fidelity"]["attempts"] == 2
    assert pack["meta"]["fidelity"]["kept_attempt"] == 1
    assert pack["meta"]["fidelity"]["tone_corr"] == pytest.approx(1.0, abs=1e-5)


def test_openai_provider_mocked(monkeypatch):
    monkeypatch.setenv("BOTDRAW_GENERATIVE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import botdraw.portrait.generative as gen

    ink = np.zeros((40, 32), dtype=np.float32)
    ink[10:30, 8:24] = 1.0
    with patch.object(
        gen,
        "_openai_ink",
        return_value=(ink, {"provider": "openai", "model": "gpt-image-1"}),
    ):
        pack = generate_portrait_ink(
            np.full((40, 32, 3), 180, dtype=np.float32),
            provider="openai",
            allow_retry=False,
        )
        assert pack is not None
        assert pack["meta"]["provider"] == "openai"


def test_gemini_provider_mocked(monkeypatch):
    monkeypatch.setenv("BOTDRAW_GENERATIVE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import botdraw.portrait.generative as gen

    ink = np.zeros((40, 32), dtype=np.float32)
    ink[5:35, 5:27] = 0.8
    with patch.object(
        gen,
        "_gemini_ink",
        return_value=(ink, {"provider": "gemini", "model": "gemini-test"}),
    ):
        pack = generate_portrait_ink(
            np.full((40, 32, 3), 180, dtype=np.float32),
            provider="gemini",
            allow_retry=False,
        )
        assert pack is not None
        assert pack["meta"]["provider"] == "gemini"


def test_ingest_generative_manual(line_ink_path):
    pv = ingest_portrait(
        mode="photo",
        quality="booth-fast",
        paper="A5",
        line_source="generative",
        generative_provider="manual",
        generative_ink_path=str(line_ink_path),
        ensemble=False,
        auto_frame=False,
    )
    assert pv.meta.get("line_source") == "generative"
    assert pv.meta.get("edge_extractor") == "generative_ink"
    assert (pv.meta.get("edge_count") or 0) > 0
    assert pv.meta.get("generative_fidelity") is not None
    assert pv.meta.get("generative", {}).get("provider") == "manual"


def test_ingest_generative_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setenv("BOTDRAW_GENERATIVE_PROVIDER", "manual")
    monkeypatch.delenv("BOTDRAW_GENERATIVE_INK", raising=False)
    pv = ingest_portrait(
        mode="photo",
        quality="booth-fast",
        paper="A5",
        line_source="generative",
        generative_provider="manual",
        ensemble=False,
        auto_frame=False,
    )
    assert pv.meta.get("line_source") in ("classic", "neural")
    assert pv.meta.get("line_source_warning")
    assert "BOTDRAW_GENERATIVE_INK" in (pv.meta.get("line_source_warning") or "")


def test_ink_tone_corr_sanity():
    a = np.zeros((10, 10), dtype=np.float32)
    a[2:8, 2:8] = 1.0
    assert ink_tone_corr(a, a) == pytest.approx(1.0, abs=1e-5)
    assert ink_tone_corr(a, 1.0 - a) < 0
