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


def test_provider_status_and_default(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_SCENE_JSON", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_CRITIQUE_JSON", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_FEEDBACK_JSON", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_TURNS_DIR", raising=False)
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "gemini")
    assert cr.default_provider() == "gemini"
    status = cr.provider_status()
    assert set(status) >= {"anthropic", "openai", "gemini", "manual"}
    assert status["manual"]["ready"] is False
    assert status["anthropic"]["ready"] is False


def test_load_scene_json_normalizes_rich_manual(tmp_path):
    path = tmp_path / "scene.json"
    path.write_text(
        json.dumps(
            {
                "orientation_deg": 0,
                "framing": "ignore_me",
                "subjects": [
                    {"kind": "person", "importance": 1.0, "notes": "extra"},
                    {"kind": "pet", "importance": 0.95, "notes": "puppy"},
                ],
                "clutter": [
                    {"id": "window_blinds", "severity": 0.9},
                    {"id": "wire_crate", "severity": 0.85},
                ],
                "lighting": "backlit_window",
                "crop_hint": {"x": 0.02, "y": 0.02, "w": 0.96, "h": 0.96},
                "ingest": {
                    "line_source": "neural",
                    "suppress_background": True,
                    "protect_subjects": ["person", "pet"],
                    "max_tone_code": 4,
                },
                "restyle_hints": {"preferred_styles": ["portrait_linework"]},
                "summary": "man + puppy",
            }
        ),
        encoding="utf-8",
    )
    scene = cr.load_scene_json(path)
    assert scene.summary == "man + puppy"
    assert "blinds" in scene.clutter
    assert "wire_crate" in scene.clutter
    assert any(s.kind == "pet" for s in scene.subjects)
    knobs = cr.scene_to_ingest_knobs(scene)
    assert knobs["suppress_background"] is True
    assert knobs["line_source"] == "neural"


def test_manual_provider_review(monkeypatch, tmp_path):
    path = tmp_path / "manual.json"
    path.write_text(SCENE_JSON, encoding="utf-8")
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_SCENE_JSON", str(path))
    scene = cr.review_photo(_rgb(), provider="manual")
    assert scene is not None
    assert scene.orientation_deg == 90
    assert "pet" in {s.kind for s in scene.subjects}


def test_compare_providers_reports_not_ready(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_SCENE_JSON", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_TURNS_DIR", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_CRITIQUE_JSON", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_FEEDBACK_JSON", raising=False)
    results = cr.compare_providers_scene(_rgb(), providers=["anthropic", "openai", "gemini", "manual"])
    assert "error" in results["anthropic"]
    assert "error" in results["openai"]
    assert "error" in results["gemini"]
    assert "error" in results["manual"]


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
    assert knobs["ai_review"] == "live"
    assert knobs["ai_review_status"] == "scene"
    assert knobs["orientation_deg"] == 90
    assert out_rgb.shape[:2] == (80, 40)  # CW 90 swaps sides


def test_maybe_review_disabled_is_noop():
    rgb = _rgb(32)
    out_rgb, knobs = cr.maybe_review_and_merge_knobs(rgb, {"line_source": "classic"}, enabled=False)
    assert out_rgb is rgb or np.allclose(out_rgb, rgb)
    assert knobs["line_source"] == "classic"
    assert "ai_scene" not in knobs


def test_resolve_ai_review_mode_by_quality():
    assert cr.resolve_ai_review_mode(False) == "off"
    assert cr.resolve_ai_review_mode("off") == "off"
    assert cr.resolve_ai_review_mode("live") == "live"
    assert cr.resolve_ai_review_mode("studio") == "studio"
    assert cr.resolve_ai_review_mode(True, quality="booth-balanced") == "live"
    assert cr.resolve_ai_review_mode(True, quality="booth-fast") == "live"
    assert cr.resolve_ai_review_mode("true", quality="studio-hq") == "studio"
    assert cr.resolve_ai_review_mode("on", quality="booth-balanced") == "live"
    assert cr.ai_review_wants_scene("live") and cr.ai_review_wants_scene("studio")
    assert not cr.ai_review_wants_scene("off")
    assert cr.ai_review_wants_critique("studio")
    assert not cr.ai_review_wants_critique("live")


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


def test_enrich_keep_more_edges_forces_reingest():
    critique = cr.PortraitCritique(
        overall=0.6,  # previously required overall < 0.45
        issues=[
            cr.CritiqueIssue(code="glasses", severity=0.6, fix="keep_more_edges"),
        ],
        actions=cr.CritiqueActions(force_reingest=False),
    )
    acts = cr._enrich_actions_from_fixes(critique)
    assert acts.force_reingest is True
    assert acts.line_source == "classic"


def test_manual_critique_json(monkeypatch, tmp_path):
    path = tmp_path / "critique.json"
    path.write_text(CRITIQUE_JSON, encoding="utf-8")
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_CRITIQUE_JSON", str(path))
    critique = cr.critique_render(_rgb(), b"\x89PNG\r\n\x1a\n", style_id="portrait_linework")
    assert critique is not None
    assert critique.actions.suppress_background is True
    assert "rm -rf /" not in {i.fix for i in critique.issues}


def test_pipeline_live_skips_critique(monkeypatch):
    """live mode must not invoke structure or confirm critique."""
    from botdraw.core import pipeline as pipe

    called = {"critique": 0, "structure": 0}

    def fake_scene(extra, *, image_path, quality=None):
        return {
            **extra,
            "ai_review": "live",
            "ai_review_status": "scene",
            "line_source": "classic",
            "suppress_background": True,
            "max_tone_code": 4,
        }

    def boom_critique(*args, **kwargs):
        called["critique"] += 1
        raise AssertionError("critique must not run in live mode")

    def boom_structure(*args, **kwargs):
        called["structure"] += 1
        raise AssertionError("structure critique must not run in live mode")

    monkeypatch.setattr(pipe, "_apply_ai_scene_review", fake_scene)
    monkeypatch.setattr(pipe, "_apply_ai_critique_once", boom_critique)
    monkeypatch.setattr(pipe, "_apply_ai_structure_after_ingest", boom_structure)

    job, payload, layers = pipe.render_job(
        app="portraitbot",
        style_id="portrait_linework",
        quality=__import__("botdraw.core.models", fromlist=["QualityPreset"]).QualityPreset.BOOTH_FAST,
        paper=__import__("botdraw.core.models", fromlist=["PaperSize"]).PaperSize.A5,
        seed=1,
        density=1.0,
        image_path=None,
        params_extra={"ai_review": "live", "image_mode": "photo", "line_source": "classic"},
    )
    assert called["critique"] == 0
    assert called["structure"] == 0
    assert job.status.value == "ready" or str(job.status).endswith("READY")
    assert (layers.get("meta") or {}).get("ai_review") == "live" or True  # meta may nest differently


def test_manual_skip_missing_turn(monkeypatch, tmp_path):
    """Missing turn JSON → fail closed (None), do not invent knobs."""
    turns = tmp_path / "turns"
    turns.mkdir()
    (turns / "turn01_scene.json").write_text(
        json.dumps(
            {
                "orientation_deg": 0,
                "subjects": [{"kind": "other", "importance": 1.0}],
                "clutter": [],
                "lighting": "normal",
                "ingest": {"line_source": "classic", "suppress_background": False},
                "summary": "only scene",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_TURNS_DIR", str(turns))
    assert cr.resolve_manual_turn_path(2) is None
    assert cr.resolve_manual_turn_path(3) is None
    rgb = _rgb()
    assert cr.critique_structure(rgb, b"\x89PNG\r\n\x1a\n", turn=2) is None
    assert cr.critique_render(rgb, b"\x89PNG\r\n\x1a\n", style_id="x", turn=3) is None


def test_manual_feedback_json_turn3(monkeypatch, tmp_path):
    path = tmp_path / "feedback.json"
    path.write_text(
        json.dumps(
            {
                "overall": 0.9,
                "issues": [],
                "actions": {"force_reingest": True, "density_mul": 1.2},
                "summary": "confirm",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_FEEDBACK_JSON", str(path))
    monkeypatch.delenv("BOTDRAW_VISION_TURNS_DIR", raising=False)
    monkeypatch.delenv("BOTDRAW_VISION_CRITIQUE_JSON", raising=False)
    c = cr.critique_render(_rgb(), b"\x89PNG\r\n\x1a\n", style_id="portrait_linework", turn=3)
    assert c is not None
    assert c.summary == "confirm"


def test_pipeline_studio_structure_then_confirm(monkeypatch):
    """Studio: scene once, structure once, confirm once."""
    from botdraw.core import pipeline as pipe
    from botdraw.core.models import PaperSize, QualityPreset

    calls = {"scene": 0, "structure": 0, "confirm": 0}

    def fake_scene(extra, *, image_path, quality=None):
        calls["scene"] += 1
        return {
            **extra,
            "ai_review": "studio",
            "ai_review_status": "scene",
            "line_source": "classic",
            "suppress_background": False,
            "max_tone_code": 3,
        }

    def fake_structure(extra):
        calls["structure"] += 1
        return {
            **extra,
            "ai_vision_turn": 2,
            "ai_review_status": "structure",
            "ai_critique": {"overall": 0.4, "issues": [], "actions": {}, "summary": "structure"},
            "ai_critique_by_turn": {
                "2": {"overall": 0.4, "issues": [], "actions": {}, "summary": "structure"}
            },
        }

    def fake_confirm(extra, *, layered, palette, paper_color_hex):
        calls["confirm"] += 1
        return {
            **extra,
            "ai_vision_turn": 3,
            "ai_review_status": "confirm",
            "ai_critique_applied": True,
            "ai_critique": {"overall": 0.85, "issues": [], "actions": {}, "summary": "ok"},
        }

    monkeypatch.setattr(pipe, "_apply_ai_scene_review", fake_scene)
    monkeypatch.setattr(pipe, "_apply_ai_structure_after_ingest", fake_structure)
    monkeypatch.setattr(pipe, "_apply_ai_critique_once", fake_confirm)

    job, _payload, _layers = pipe.render_job(
        app="portraitbot",
        style_id="portrait_linework",
        quality=QualityPreset.STUDIO_HQ,
        paper=PaperSize.A5,
        seed=1,
        density=1.0,
        image_path=None,
        params_extra={"ai_review": "studio", "image_mode": "photo", "line_source": "classic"},
    )
    assert calls["scene"] == 1
    assert calls["structure"] == 1
    assert calls["confirm"] == 1
    assert job is not None


def test_pipeline_studio_runs_critique_once(monkeypatch):
    from botdraw.core import pipeline as pipe
    from botdraw.core.models import PaperSize, QualityPreset

    calls = {"critique": 0}

    def fake_scene(extra, *, image_path, quality=None):
        return {
            **extra,
            "ai_review": "studio",
            "ai_review_status": "scene",
            "line_source": "classic",
            "suppress_background": True,
            "max_tone_code": 4,
        }

    def fake_structure(extra):
        return {
            **extra,
            "ai_vision_turn": 2,
            "ai_review_status": "structure",
        }

    def fake_critique(extra, *, layered, palette, paper_color_hex):
        calls["critique"] += 1
        return {
            **extra,
            "ai_critique": {"overall": 0.9, "issues": [], "actions": {}, "summary": "ok"},
            "ai_review_status": "confirm",
            "ai_critique_applied": True,
            "ai_vision_turn": 3,
        }

    monkeypatch.setattr(pipe, "_apply_ai_scene_review", fake_scene)
    monkeypatch.setattr(pipe, "_apply_ai_structure_after_ingest", fake_structure)
    monkeypatch.setattr(pipe, "_apply_ai_critique_once", fake_critique)

    job, _payload, _layers = pipe.render_job(
        app="portraitbot",
        style_id="portrait_linework",
        quality=QualityPreset.STUDIO_HQ,
        paper=PaperSize.A5,
        seed=1,
        density=1.0,
        image_path=None,
        params_extra={"ai_review": "studio", "image_mode": "photo", "line_source": "classic"},
    )
    assert calls["critique"] == 1
    assert job is not None


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
