"""Contact-sheet builder: the human-review surface for portrait fidelity."""
from __future__ import annotations

from pathlib import Path

from botdraw.core.models import QualityPreset
from botdraw.portrait.scoreboard import build_contact_sheet, render_contact_sheet_html, write_contact_sheet

FIXTURE = Path(__file__).parent / "fixtures" / "portrait" / "photos" / "armstrong_headshot.jpg"


def test_build_contact_sheet_scores_every_requested_style():
    result = build_contact_sheet(
        FIXTURE,
        styles=["portrait_linework", "portrait_cubism"],
        quality=QualityPreset.BOOTH_BALANCED,
    )
    assert result.line_source_resolved in ("classic", "neural")
    ids = [s.style_id for s in result.scores]
    assert ids == ["portrait_linework", "portrait_cubism"]
    for s in result.scores:
        assert s.preview_png_b64
        assert s.path_count > 0


def test_render_html_embeds_every_preview_image():
    result = build_contact_sheet(
        FIXTURE, styles=["portrait_linework"], quality=QualityPreset.BOOTH_BALANCED
    )
    out = render_contact_sheet_html(result)
    assert "portrait_linework" in out
    assert result.scores[0].preview_png_b64 in out
    assert result.source_png_b64 in out


def test_write_contact_sheet_writes_html_and_slim_json_sidecar(tmp_path):
    out_html = tmp_path / "sheet.html"
    path, result = write_contact_sheet(
        FIXTURE,
        out_html,
        styles=["portrait_linework"],
        quality=QualityPreset.BOOTH_BALANCED,
    )
    assert path == out_html
    assert out_html.exists()
    sidecar = tmp_path / "sheet.json"
    assert sidecar.exists()
    import json

    payload = json.loads(sidecar.read_text())
    assert "preview_png_b64" not in json.dumps(payload)
    assert "source_png_b64" not in payload
    assert payload["scores"][0]["style_id"] == "portrait_linework"
