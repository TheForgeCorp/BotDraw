"""Best-of-N seeded variant selection: render + sheet + optional vision ranking."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from botdraw.core.models import QualityPreset
from botdraw.portrait.claude_review import VariantSelection, select_best_variant
from botdraw.portrait.variant_selection import (
    render_seeded_variants,
    render_selection_html,
    write_selection_sheet,
)

FIXTURE = Path(__file__).parent / "fixtures" / "portrait" / "gold" / "people" / "person-front.png"


def test_render_seeded_variants_uses_distinct_seeds():
    variants, previews = render_seeded_variants(
        FIXTURE, "portrait_dots", n=3, seed0=10, quality=QualityPreset.BOOTH_FAST
    )
    assert [v.seed for v in variants] == [10, 11, 12]
    assert len(previews) == 3
    assert all(len(p) > 0 for p in previews)
    assert all(v.preview_png_b64 for v in variants)


def test_render_seeded_variants_produces_visually_different_previews():
    """A seed-sensitive style (stipple-based dots) must actually vary its
    dot placement across seeds — otherwise 'best-of-N' has nothing to
    choose between."""
    _variants, previews = render_seeded_variants(
        FIXTURE, "portrait_dots", n=3, seed0=1, quality=QualityPreset.BOOTH_FAST
    )
    assert len({p for p in previews}) == len(previews), "expected distinct raster bytes per seed"


def test_write_selection_sheet_without_vision(tmp_path):
    out_html = tmp_path / "sheet.html"
    path, result = write_selection_sheet(
        FIXTURE, out_html, style_id="portrait_linework", n=2, quality=QualityPreset.BOOTH_FAST
    )
    assert path == out_html
    assert out_html.exists()
    assert result.vision_best_index is None
    html_text = out_html.read_text()
    assert "No vision provider ready" in html_text

    sidecar = tmp_path / "sheet.json"
    payload = json.loads(sidecar.read_text())
    assert "preview_png_b64" not in json.dumps(payload)
    assert len(payload["variants"]) == 2


def test_render_selection_html_marks_vision_pick():
    from botdraw.portrait.variant_selection import SelectionResult, Variant

    result = SelectionResult(
        photo="photo.jpg",
        style_id="portrait_linework",
        quality="booth-fast",
        generated_at="2026-01-01T00:00:00+00:00",
        source_png_b64="",
        variants=[
            Variant(seed=1, path_count=10, preview_png_b64=""),
            Variant(seed=2, path_count=12, preview_png_b64=""),
        ],
        vision_best_index=1,
        vision_reasoning="clearer jawline",
        vision_confidence=0.8,
    )
    out = render_selection_html(result)
    assert "VISION PICK" in out
    assert "clearer jawline" in out
    assert "seed 2" in out.lower() or "Seed 2" in out


def _stub_client(**kwargs) -> str:
    return json.dumps(
        {"best_index": 1, "ranked_indices": [1, 0], "reasoning": "closer likeness", "confidence": 0.77}
    )


def test_select_best_variant_with_stubbed_vision_client():
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    previews = [b"fakepng0", b"fakepng1"]
    selection = select_best_variant(rgb, previews, client_call=_stub_client)
    assert isinstance(selection, VariantSelection)
    assert selection.best_index == 1
    assert selection.confidence == pytest.approx(0.77)


def test_select_best_variant_rejects_out_of_range_index():
    def bad_client(**kwargs) -> str:
        return json.dumps({"best_index": 99, "ranked_indices": [99]})

    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    selection = select_best_variant(rgb, [b"a", b"b"], client_call=bad_client)
    assert selection is None


def test_select_best_variant_empty_list_returns_none():
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    assert select_best_variant(rgb, [], client_call=_stub_client) is None


def test_select_best_variant_manual_mode_reads_env_file(tmp_path, monkeypatch):
    reply = tmp_path / "selection.json"
    reply.write_text(json.dumps({"best_index": 0, "ranked_indices": [0, 1], "confidence": 0.9}))
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.setenv("BOTDRAW_VISION_SELECTION_JSON", str(reply))
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    selection = select_best_variant(rgb, [b"a", b"b"])
    assert selection is not None
    assert selection.best_index == 0


def test_select_best_variant_manual_mode_missing_file_fails_closed(monkeypatch):
    monkeypatch.setenv("BOTDRAW_VISION_PROVIDER", "manual")
    monkeypatch.delenv("BOTDRAW_VISION_SELECTION_JSON", raising=False)
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    assert select_best_variant(rgb, [b"a", b"b"]) is None


def test_write_selection_sheet_with_vision_uses_stubbed_selection(tmp_path, monkeypatch):
    """End-to-end: write_selection_sheet(use_vision=True) plumbs through to
    select_best_variant via the manual provider without needing an API key."""
    reply = tmp_path / "selection.json"
    reply.write_text(json.dumps({"best_index": 0, "ranked_indices": [0, 1], "confidence": 0.65, "reasoning": "test"}))
    monkeypatch.setenv("BOTDRAW_VISION_SELECTION_JSON", str(reply))

    out_html = tmp_path / "sheet.html"
    path, result = write_selection_sheet(
        FIXTURE,
        out_html,
        style_id="portrait_linework",
        n=2,
        quality=QualityPreset.BOOTH_FAST,
        use_vision=True,
        vision_provider="manual",
    )
    assert result.vision_best_index == 0
    assert result.vision_confidence == pytest.approx(0.65)
    assert "VISION PICK" in out_html.read_text()
