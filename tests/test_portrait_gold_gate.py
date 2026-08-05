"""Phase B classic gold-set gate — people + objects."""

from __future__ import annotations

from pathlib import Path

import pytest

from botdraw.portrait.gold import (
    ensure_gold_fixtures,
    load_manifest,
    run_gold_case,
    run_gold_set,
    write_gold_report,
)


@pytest.fixture(scope="module")
def gold_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("portrait-gold")
    ensure_gold_fixtures(root=root, force=True)
    return root


def test_gold_manifest_has_people_and_objects(gold_root: Path):
    cases = load_manifest(gold_root)
    cats = {c.category for c in cases}
    assert "people" in cats
    assert "objects" in cats
    assert len(cases) >= 4
    for c in cases:
        assert (gold_root / c.file).is_file()


@pytest.mark.parametrize("case_id", ["person-front", "object-mug", "object-camera", "object-chair"])
def test_gold_case_classic_gate(gold_root: Path, case_id: str):
    case = next(c for c in load_manifest(gold_root) if c.id == case_id)
    result = run_gold_case(case, root=gold_root)
    assert result.line_source == "classic"
    assert result.hatch_count == 0
    assert result.edge_count >= case.min_edges
    assert "layer-edges" in result.raw_svg
    assert result.passed, [c for c in result.checks if not c.passed]


def test_gold_set_all_pass(gold_root: Path):
    results = run_gold_set(root=gold_root)
    failed = [r.case.id for r in results if not r.passed]
    assert not failed, failed


def test_gold_report_html_writes(gold_root: Path, tmp_path: Path):
    out = tmp_path / "gold.html"
    path, results = write_gold_report(out, root=gold_root)
    text = path.read_text(encoding="utf-8")
    assert "PortraitBot Phase B" in text
    assert "layer-edges" in text
    assert all(r.case.id in text for r in results)
    assert "vision-loop" not in text


def test_gold_report_with_vision_fixtures(gold_root: Path, tmp_path: Path):
    out = tmp_path / "gold-vision.html"
    path, results = write_gold_report(out, root=gold_root, with_vision_fixtures=True)
    text = path.read_text(encoding="utf-8")
    assert "vision-loop" in text
    assert "Studio vision loop" in text
    assert "pass 1" in text and "pass 3" in text
    assert "structure" in text or "confirm" in text
    # Classic gate still present and AI-off for cases
    assert all(r.case.id in text for r in results)
    slim = path.parent / "gold-vision-vision.json"
    assert slim.exists()
    import json

    rows = json.loads(slim.read_text(encoding="utf-8"))
    assert any(r.get("turn") == 3 for r in rows)
