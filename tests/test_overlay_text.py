"""Page text overlay + Phyllotaxis mark_size_mm regressions."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.jobs import artifact_dir
from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.letters import HERSHEY_LIKE, layout_text
from botdraw.palettes import load_palette
from botdraw.styles import ensure_styles_loaded, get_style
from botdraw.styles.geom import mark_polylines


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_mark_polylines_outer_size_mm():
    """mark_size_mm is full outer extent: circle diameter / square side / star diameter."""
    import math

    size = 2.5
    star = mark_polylines(0, 0, size, "star")
    assert len(star) == 1
    assert star[0][1] is True
    assert len(star[0][0]) == 11
    # Tip at top: outer radius = size/2
    tip = star[0][0][0]
    assert abs(math.hypot(tip[0], tip[1]) - size / 2) < 0.05

    cross = mark_polylines(0, 0, size, "cross")
    assert len(cross) == 2
    assert all(not closed for _, closed in cross)
    assert all(len(pts) == 2 for pts, _ in cross)
    assert abs(cross[0][0][1][0] - cross[0][0][0][0] - size) < 0.05

    circle = mark_polylines(0, 0, size, "circle")
    assert len(circle[0][0]) == 21  # 20 + close
    cw, ch = _bbox(circle[0][0])
    assert abs(cw - size) < 0.05
    assert abs(ch - size) < 0.05

    square = mark_polylines(0, 0, size, "square")
    qw, qh = _bbox(square[0][0])
    assert abs(qw - size) < 0.05
    assert abs(qh - size) < 0.05


def test_phyllotaxis_mark_size_mm():
    ensure_styles_loaded()
    palette = load_palette("default-6")
    layered = get_style("phyllotaxis").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            extra={"n_points": 80, "mark": "square", "mark_size_mm": 2.5},
        ),
        paper=PaperSize.A5,
    )
    assert layered.meta["mark_size_mm"] == 2.5
    assert layered.meta["mark"] == "square"
    assert layered.meta["strokes"] == 80
    pts = layered.passes[0].polylines[10].points
    w, h = _bbox(pts)
    assert abs(w - 2.5) < 0.05
    assert abs(h - 2.5) < 0.05

    cross = get_style("phyllotaxis").render(
        palette=palette,
        params=StyleParams(
            seed=1,
            quality=QualityPreset.BOOTH_FAST,
            density=1.0,
            extra={"n_points": 50, "mark": "cross", "mark_size_mm": 2.5},
        ),
        paper=PaperSize.A5,
    )
    assert cross.meta["n_points"] == 50
    assert cross.meta["strokes"] == 100  # 2 strokes per seed


def test_hershey_digits():
    for d in "0123456789":
        assert d in HERSHEY_LIKE
        assert HERSHEY_LIKE[d]
    polys, _ = layout_text("Line 1", x=12, y=14, size_mm=5, pen_id="black")
    assert len(polys) >= 5


def test_overlay_text_add_replace_move():
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
            "x_mm": 12,
            "y_mm": 14,
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
    page_pass = next(p for p in body["layers"]["passes"] if p["id"] == "page-text")
    assert page_pass["polyline_count"] > 0

    moved = client.post(
        f"/api/jobs/{job_id}/overlay-text",
        json={
            "lines": ["Hello", "BotDraw", "Lab"],
            "x_mm": 40,
            "y_mm": 20,
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
