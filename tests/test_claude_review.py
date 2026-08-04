"""Anthropic vision review: schemas, knob mapping, mocked client (no live API)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from botdraw.portrait import claude_review as cr


def _rgb(size: int = 64) -> np.ndarray:
    return np.full((size, size, 3), 180.0, dtype=np.float32)


SCENE_JSON = json.dumps(
    {
        "orientation_deg": 90,
        "subjects": [
            {"kind": "person", "importance": 1.0},
            {"kind": "pet", "importance": 0.9},
        ],
        "clutter": ["wire_crate", "blinds"],
        "lighting": "backlit_window",
        "crop_hint": {"x": 0.05, "y": 0.0, "w": 0.9, "h": 1.0},
        "ingest": {
            "line_source": "neural",
            "suppress_background": True,
            "protect_subjects": ["person", "pet"],
            "max_tone_code": 4,
        },
        "summary": "Man and puppy with crate clutter",
    }
)

CRITIQUE_JSON = json.dumps(
    {
        "overall": 0.55,
        "issues": [
            {
                "code": "background_noise",
                "severity": 0.8,
                "region": "crate",
                "fix": "suppress_background",
            },
            {
                "code": "texture_flat",
                "severity": 0.7,
                "region": "pet_fur",
                "fix": "boost_pet_shade",
            },
            {
                "code": "hack",
                "severity": 0.9,
                "region": None,
                "fix": "rm -rf /",  # must be dropped
            },
        ],
        "actions": {
            "force_reingest": False,
            "line_source": "neural",
            "hatch_budget_mul": 1.3,
            "style_id": "portrait_scribble_tone",
            "max_tone_code": 4,
            "suppress_background": True,
            "density_mul": 1.1,
        },
        "summary": "Crate still loud; boost fur shade",
    }
)


def test_claude_available_false_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not cr.claude_available()


def test_review_photo_parses_scene_via_stub():
    def stub(**kwargs):
        return SCENE_JSON

    scene = cr.review_photo(_rgb(), client_call=stub)
    assert scene is not None
    assert scene.orientation_deg == 90
    assert any(s.kind == "pet" for s in scene.subjects)
    assert "wire_crate" in scene.clutter
    assert scene.ingest.line_source == "neural"


def test_review_photo_fail_closed_on_bad_json():
    def stub(**kwargs):
        return "not json at all"

    assert cr.review_photo(_rgb(), client_call=stub) is None


def test_scene_to_ingest_knobs_maps_closed_dict():
    scene = cr.PortraitScene.model_validate(json.loads(SCENE_JSON))
    knobs = cr.scene_to_ingest_knobs(scene)
    assert knobs["line_source"] == "neural"
    assert knobs["suppress_background"] is True
    assert knobs["orientation_deg"] == 90
    assert "pet" in knobs["protect_subjects"]
    assert knobs["crop"]["source"] == "ai_scene"
    assert knobs["auto_frame"] is False


def test_apply_orientation_rotates():
    rgb = np.zeros((40, 80, 3), dtype=np.float32)
    rgb[:, :10] = 255  # left strip
    out = cr.apply_orientation(rgb, 90)
    # CW 90: original width becomes height
    assert out.shape[0] == 80 and out.shape[1] == 40


def test_critique_filters_unknown_fixes():
    def stub(**kwargs):
        return CRITIQUE_JSON

    critique = cr.critique_render(_rgb(), b"\x89PNG\r\n\x1a\n", style_id="portrait_linework", client_call=stub)
    assert critique is not None
    fixes = {i.fix for i in critique.issues}
    assert "suppress_background" in fixes
    assert "boost_pet_shade" in fixes
    assert "rm -rf /" not in fixes


def test_critique_to_render_knobs():
    critique = cr.PortraitCritique.model_validate(json.loads(CRITIQUE_JSON))
    # Drop illegal fix before mapping (as critique_render would)
    critique.issues = [i for i in critique.issues if i.fix in cr.ALLOWED_FIXES]
    knobs = cr.critique_to_render_knobs(critique)
    assert knobs["style_id"] == "portrait_scribble_tone"
    assert knobs["hatch_budget_mul"] == 1.3
    assert knobs["suppress_background"] is True


def test_maybe_review_merges_and_rotates():
    def stub(**kwargs):
        return SCENE_JSON

    rgb = np.full((40, 80, 3), 180.0, dtype=np.float32)
    out_rgb, knobs = cr.maybe_review_and_merge_knobs(
        rgb, {"line_source": "auto"}, enabled=True, client_call=stub
    )
    assert knobs["ai_review"] == "scene"
    assert knobs["orientation_deg"] == 90
    assert out_rgb.shape[:2] == (80, 40)  # CW 90 swaps sides


def test_maybe_review_disabled_is_noop():
    rgb = _rgb(32)
    out_rgb, knobs = cr.maybe_review_and_merge_knobs(rgb, {"line_source": "classic"}, enabled=False)
    assert out_rgb is rgb or np.allclose(out_rgb, rgb)
    assert knobs["line_source"] == "classic"
    assert "ai_scene" not in knobs


def test_enrich_actions_from_fixes_sets_style():
    critique = cr.PortraitCritique(
        overall=0.5,
        issues=[
            cr.CritiqueIssue(code="x", severity=0.8, fix="prefer_scribble"),
        ],
        actions=cr.CritiqueActions(),
    )
    acts = cr._enrich_actions_from_fixes(critique)
    assert acts.style_id == "portrait_scribble_tone"


def test_ingest_accepts_ai_scene_knobs():
    from botdraw.core.models import QualityPreset
    from botdraw.portrait.ingest import ingest_portrait

    pv = ingest_portrait(
        image_array=_rgb(96),
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        line_source="classic",
        orientation_deg=0,
        max_tone_code=3,
        suppress_background=True,
        protect_subjects=["person", "pet"],
        ai_scene={"summary": "test"},
    )
    assert pv.meta.get("ai_scene", {}).get("summary") == "test"
    assert pv.meta.get("protect_subjects") == ["person", "pet"]
    assert pv.meta.get("max_tone_code") == 3
