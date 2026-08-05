"""Page text overlay + Phyllotaxis mark_size_mm regressions."""

from __future__ import annotations

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.styles import ensure_styles_loaded, get_style
from botdraw.styles.geom import mark_polylines


def test_mark_polylines_shapes():
    star = mark_polylines(0, 0, 2.5, "star")
    assert len(star) == 1
    assert star[0][1] is True
    assert len(star[0][0]) == 11

    cross = mark_polylines(0, 0, 2.5, "cross")
    assert len(cross) == 2
    assert all(not closed for _, closed in cross)
    assert all(len(pts) == 2 for pts, _ in cross)

    circle = mark_polylines(0, 0, 2.5, "circle")
    assert len(circle[0][0]) == 21  # 20 + close


def test_phyllotaxis_mark_size_mm():
    ensure_styles_loaded()
    palette = load_palette("default-6")
    layered = get_style("phyllotaxis").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            extra={"n_points": 80, "mark": "star", "mark_size_mm": 3.0},
        ),
        paper=PaperSize.A5,
    )
    assert layered.meta["mark_size_mm"] == 3.0
    assert layered.meta["mark"] == "star"
    assert layered.meta["strokes"] == 80

    cross = get_style("phyllotaxis").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            # n_points floor is 50 (UI/engine knob range)
            extra={"n_points": 50, "mark": "cross", "mark_size_mm": 2.5},
        ),
        paper=PaperSize.A5,
    )
    assert cross.meta["n_points"] == 50
    assert cross.meta["strokes"] == 100  # 2 strokes per seed


def test_overlay_text_add_replace_move():
    from pathlib import Path

    from botdraw.core.jobs import artifact_dir

    client = TestClient(app)
    base = client.post(
        "/api/render",
        json={
            "app": "design",
            "style_id": "phyllotaxis",
            "palette_id": "default-6",
            "paper": "A5",
            "quality": "booth-fast",
            "seed": 2,
            "density": 1.0,
            "params_extra": {"n_points": 60, "mark": "circle", "mark_size_mm": 2.5},
        },
    )
    assert base.status_code == 200
    job_id = base.json()["job"]["id"]
    strokes0 = base.json()["emulator"]["stats"]["stroke_count"]
    assert (Path(artifact_dir(job_id)) / "layered.json").exists()

    added = client.post(
        f"/api/jobs/{job_id}/overlay-text",
        json={
            "lines": ["Hello", "BotDraw", "Lab"],
            "x_mm": 20,
            "y_mm": 160,
            "size_mm": 5,
            "pen_id": "black",
            "replace_pass_id": "page-text",
        },
    )
    assert added.status_code == 200
    body = added.json()
    assert body["job"]["id"] == job_id
    assert body["page_text"]["lines"][0] == "Hello"
    assert body["emulator"]["stats"]["stroke_count"] > strokes0
    assert any(p["id"] == "page-text" for p in body["layers"]["passes"])

    moved = client.post(
        f"/api/jobs/{job_id}/overlay-text",
        json={
            "lines": ["Hello", "BotDraw", "Lab"],
            "x_mm": 40,
            "y_mm": 140,
            "size_mm": 5,
            "pen_id": "black",
            "replace_pass_id": "page-text",
        },
    )
    assert moved.status_code == 200
    assert moved.json()["page_text"]["x_mm"] == 40
    assert sum(1 for p in moved.json()["layers"]["passes"] if p["id"] == "page-text") == 1

    cleared = client.post(
        f"/api/jobs/{job_id}/overlay-text",
        json={"clear": True, "replace_pass_id": "page-text"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["page_text"] is None
    assert not any(p["id"] == "page-text" for p in cleared.json()["layers"]["passes"])
