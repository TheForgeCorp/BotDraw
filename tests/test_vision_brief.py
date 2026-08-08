"""botdraw vision brief: ready-to-paste folder for the manual subscription workflow."""
from __future__ import annotations

import json

import pytest

from botdraw.core.models import QualityPreset
from botdraw.core.pipeline import render_job
from botdraw.portrait.vision_brief import write_vision_brief


@pytest.fixture(scope="module")
def portrait_job():
    from pathlib import Path

    photo = Path(__file__).parent / "fixtures" / "portrait" / "gold" / "people" / "person-front.png"
    job, _payload, _layers = render_job(
        app="portraitbot",
        style_id="portrait_linework",
        quality=QualityPreset.BOOTH_FAST,
        seed=1,
        image_path=str(photo),
    )
    return job


def test_write_vision_brief_turn1_writes_prompt_and_readme(portrait_job, tmp_path):
    out = write_vision_brief(portrait_job.id, tmp_path / "brief", turn=1)
    assert (out / "prompt.txt").exists()
    assert (out / "README.md").exists()
    prompt = (out / "prompt.txt").read_text()
    assert "orientation_deg" in prompt  # SCENE_SYSTEM schema, not just a filename
    assert "Analyze this portrait photo" in prompt
    readme = (out / "README.md").read_text()
    assert "turn01_scene.json" in readme  # matches resolve_manual_turn_path()'s naming


def test_write_vision_brief_copies_source_and_renders_preview(portrait_job, tmp_path):
    out = write_vision_brief(portrait_job.id, tmp_path / "brief", turn=1)
    previews = list(out.glob("source.*"))
    assert previews, "expected the source photo (or synthetic fixture) to be copied"
    assert (out / "render_preview.png").exists()
    assert (out / "render_preview.png").stat().st_size > 0


def test_write_vision_brief_turn_selects_right_prompt_and_filename(portrait_job, tmp_path):
    out2 = write_vision_brief(portrait_job.id, tmp_path / "turn2", turn=2)
    prompt2 = (out2 / "prompt.txt").read_text()
    assert "structure" in prompt2.lower()
    assert "turn02_critique.json" in (out2 / "README.md").read_text()

    out3 = write_vision_brief(portrait_job.id, tmp_path / "turn3", turn=3)
    assert "turn03_critique.json" in (out3 / "README.md").read_text()


def test_write_vision_brief_rejects_unknown_turn(portrait_job, tmp_path):
    with pytest.raises(ValueError):
        write_vision_brief(portrait_job.id, tmp_path / "bad", turn=7)


def test_write_vision_brief_raises_for_missing_job(tmp_path):
    with pytest.raises(Exception):
        write_vision_brief("not-a-real-job-id", tmp_path / "brief", turn=1)


def test_vision_brief_reply_file_is_consumable_by_manual_provider(portrait_job, tmp_path, monkeypatch):
    """
    The whole point of matching resolve_manual_turn_path()'s naming: once
    the user saves their pasted reply as turnNN_<kind>.json in the brief
    folder, pointing BOTDRAW_VISION_TURNS_DIR at that folder must let the
    existing manual-provider code find it with zero extra glue.
    """
    from botdraw.portrait.claude_review import load_manual_turn

    out = write_vision_brief(portrait_job.id, tmp_path / "brief", turn=1)
    reply = {
        "orientation_deg": 0,
        "subjects": [{"kind": "person", "importance": 1.0}],
        "clutter": [],
        "lighting": "normal",
        "crop_hint": None,
        "ingest": {
            "line_source": "auto",
            "suppress_background": False,
            "protect_subjects": [],
            "max_tone_code": 4,
        },
        "summary": "test reply",
    }
    (out / "turn01_scene.json").write_text(json.dumps(reply), encoding="utf-8")
    monkeypatch.setenv("BOTDRAW_VISION_TURNS_DIR", str(out))
    scene = load_manual_turn(1)
    assert scene is not None
    assert scene.summary == "test reply"
