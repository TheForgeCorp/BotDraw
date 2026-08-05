"""Vision 3-turn feedback loop + visual history."""

from __future__ import annotations

import numpy as np

from botdraw.portrait.claude_review import (
    VISION_MAX_REINGESTS,
    VISION_MAX_TURNS,
    critique_structure,
    critique_to_render_knobs,
    load_critique_json,
    run_vision_turns,
)
from botdraw.portrait.vision_loop import (
    ensure_manual_turn_fixtures,
    run_vision_structure_loop,
    structure_preview_png,
    write_vision_history,
)


def test_vision_max_turns_is_three():
    assert VISION_MAX_TURNS == 3
    assert VISION_MAX_REINGESTS == 1


def test_ensure_three_turn_fixtures(tmp_path):
    root = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=root, force=True)
    assert (root / "turn01_scene.json").exists()
    assert (root / "turn02_critique.json").exists()
    assert (root / "turn03_critique.json").exists()
    c3 = load_critique_json(root / "turn03_critique.json")
    assert c3.actions.force_reingest is False


def test_vision_loop_three_passes(tmp_path):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    from botdraw.portrait.gold import ensure_gold_fixtures

    gold = tmp_path / "gold"
    ensure_gold_fixtures(root=gold, force=True)
    history = run_vision_structure_loop(
        image_path=gold / "objects" / "mug.png",
        max_turns=VISION_MAX_TURNS,
        turns_dir=turns,
    )
    assert len(history) == 3
    assert history[0].kind == "scene"
    assert history[1].reingest is True
    assert history[2].reingest is False
    assert history[2].overall is not None and history[2].overall >= history[1].overall


def test_run_vision_turns_orchestrator(tmp_path, monkeypatch):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_TURNS_DIR", str(turns))
    rgb = np.full((64, 64, 3), 180.0, dtype=np.float32)
    # Fake previews
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 200, 200)).save(buf, format="PNG")
    png = buf.getvalue()
    result = run_vision_turns(rgb, ingest_preview_png=png, render_preview_png=png)
    assert 1 in result["turns_applied"]
    assert 2 in result["turns_applied"]
    assert 3 in result["turns_applied"]
    assert result["reingest_allowed"] is False  # stripped after turn 3
    assert result["scene"] is not None
    assert len(result["critiques"]) == 2


def test_critique_structure_uses_turn2(tmp_path, monkeypatch):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_TURNS_DIR", str(turns))
    rgb = np.full((32, 32, 3), 160.0, dtype=np.float32)
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (240, 240, 240)).save(buf, format="PNG")
    c = critique_structure(rgb, buf.getvalue(), turn=2)
    assert c is not None
    knobs = critique_to_render_knobs(c)
    assert knobs.get("force_reingest") is True
    assert knobs.get("line_source") == "classic"


def test_vision_history_html_three_passes(tmp_path):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    from botdraw.portrait.gold import ensure_gold_fixtures

    gold = tmp_path / "gold"
    ensure_gold_fixtures(root=gold, force=True)
    out = tmp_path / "history.html"
    path, history = write_vision_history(
        out,
        image_path=gold / "objects" / "mug.png",
        max_turns=3,
        turns_dir=turns,
    )
    text = path.read_text(encoding="utf-8")
    assert "Pass 1" in text and "Pass 3" in text
    assert "Pass 10" not in text
    assert len(history) == 3
    assert history[1].kind == "structure"
    assert history[2].kind == "confirm"


def test_ensure_fixtures_drops_legacy_turns(tmp_path):
    root = tmp_path / "turns"
    root.mkdir()
    (root / "turn10_critique.json").write_text("{}", encoding="utf-8")
    ensure_manual_turn_fixtures(root=root, force=True)
    assert not (root / "turn10_critique.json").exists()
    assert (root / "turn03_critique.json").exists()
    names = sorted(p.name for p in root.glob("*.json"))
    assert names == ["turn01_scene.json", "turn02_critique.json", "turn03_critique.json"]
