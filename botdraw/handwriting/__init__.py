"""Handwriting clone — capture samples and replay as a simple stroke font."""

from __future__ import annotations

import json
from pathlib import Path

from botdraw.core.models import LayeredSVG, PAPER_MM, PaperSize, Polyline
from botdraw.core.svg import make_pass
from botdraw.palettes import load_palette

STORE = Path(__file__).resolve().parents[2] / "jobs" / "handwriting"


def _path(user_id: str) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    return STORE / f"{user_id}.json"


def save_samples(user_id: str, glyphs: dict[str, list[list[list[float]]]]) -> Path:
    """
    glyphs: { "A": [ [[x,y],...], ...strokes ], ... } in unit square-ish coords 0..10
    """
    path = _path(user_id)
    path.write_text(json.dumps({"user_id": user_id, "glyphs": glyphs}, indent=2), encoding="utf-8")
    return path


def load_samples(user_id: str) -> dict:
    path = _path(user_id)
    if not path.exists():
        return {"user_id": user_id, "glyphs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def render_with_clone(
    text: str,
    user_id: str,
    *,
    palette_id: str = "wedding-highlight",
    paper: PaperSize = PaperSize.A5,
    seed: int = 3,
) -> LayeredSVG:
    data = load_samples(user_id)
    glyphs = data.get("glyphs", {})
    palette = load_palette(palette_id)
    pen = palette.pens[0]
    pw, ph = PAPER_MM[paper]
    x, y = 18.0, 24.0
    scale = 0.45
    polys: list[Polyline] = []
    for ch in text:
        if ch == "\n":
            x = 18.0
            y += 8
            continue
        if ch == " ":
            x += 3
            continue
        strokes = glyphs.get(ch) or glyphs.get(ch.upper()) or [[[0, 0], [8, 8]]]
        for stroke in strokes:
            pts = [(x + p[0] * scale, y + p[1] * scale) for p in stroke]
            if len(pts) >= 2:
                polys.append(Polyline(points=pts, pen_id=pen.id))
        x += 5
        if x > pw - 20:
            x = 18.0
            y += 8
    return LayeredSVG(
        width_mm=pw,
        height_mm=ph,
        passes=[make_pass("handwriting", "Cloned hand", pen.id, polys)],
        seed=seed,
        meta={"handwriting_user": user_id},
    )
