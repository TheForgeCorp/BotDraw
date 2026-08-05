"""Vision feedback loop (10 turns) + visual history."""

from __future__ import annotations

from botdraw.portrait.claude_review import VISION_MAX_TURNS, critique_to_render_knobs, load_critique_json
from botdraw.portrait.vision_loop import (
    ensure_manual_turn_fixtures,
    run_vision_structure_loop,
    write_vision_history,
)


def test_ensure_ten_turn_fixtures(tmp_path):
    root = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=root, force=True)
    assert (root / "turn01_scene.json").exists()
    for i in range(2, 11):
        assert (root / f"turn{i:02d}_critique.json").exists()
    # scores should trend upward
    scores = []
    for i in range(2, 11):
        c = load_critique_json(root / f"turn{i:02d}_critique.json")
        scores.append(c.overall)
    assert scores[-1] >= scores[0]
    assert len(scores) == 9


def test_vision_loop_builds_history(tmp_path):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    from botdraw.portrait.gold import ensure_gold_fixtures

    gold = tmp_path / "gold"
    ensure_gold_fixtures(root=gold, force=True)
    mug = gold / "objects" / "mug.png"
    history = run_vision_structure_loop(
        image_path=mug,
        max_turns=VISION_MAX_TURNS,
        turns_dir=turns,
    )
    assert len(history) == VISION_MAX_TURNS
    assert history[0].kind == "scene"
    assert history[0].preview_png_b64
    # At least one re-ingest in early passes
    assert any(p.reingest for p in history[1:7])
    # Overall rises across critiques
    scored = [p.overall for p in history if p.overall is not None]
    assert scored[-1] >= scored[0]


def test_vision_history_html(tmp_path):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    from botdraw.portrait.gold import ensure_gold_fixtures

    gold = tmp_path / "gold"
    ensure_gold_fixtures(root=gold, force=True)
    out = tmp_path / "history.html"
    path, history = write_vision_history(
        out,
        image_path=gold / "objects" / "mug.png",
        max_turns=10,
        turns_dir=turns,
    )
    text = path.read_text(encoding="utf-8")
    assert "Pass 1" in text and "Pass 10" in text
    assert "data:image/png;base64," in text
    assert len(history) == 10


def test_critique_knobs_include_scan_and_simplify(tmp_path):
    turns = tmp_path / "turns"
    ensure_manual_turn_fixtures(root=turns, force=True)
    c = load_critique_json(turns / "turn02_critique.json")
    knobs = critique_to_render_knobs(c)
    assert knobs.get("force_reingest") is True
    assert knobs.get("scan_mode") == "edges"
    assert knobs.get("contour_simplify") == 1
    assert knobs.get("line_source") == "classic"
