"""Fractals category — scaffold starter engines (expand later)."""

from __future__ import annotations

import math

from botdraw.core.models import LayeredSVG, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register


def _koch_edge(p0: tuple[float, float], p1: tuple[float, float], depth: int) -> list[tuple[float, float]]:
    if depth <= 0:
        return [p0, p1]
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = (x1 - x0) / 3.0, (y1 - y0) / 3.0
    a = (x0 + dx, y0 + dy)
    c = (x0 + 2 * dx, y0 + 2 * dy)
    # Peak of the Koch bump (rotate middle third +60°)
    mx, my = a[0] + dx / 2, a[1] + dy / 2
    px = mx - dy * math.sqrt(3) / 2
    py = my + dx * math.sqrt(3) / 2
    b = (px, py)
    return (
        _koch_edge(p0, a, depth - 1)[:-1]
        + _koch_edge(a, b, depth - 1)[:-1]
        + _koch_edge(b, c, depth - 1)[:-1]
        + _koch_edge(c, p1, depth - 1)
    )


class _KochSnowflake:
    id = "koch_snowflake"
    name = "Koch Snowflake"
    category = "fractals"
    description = "Scaffold: classic Koch snowflake outline (fractals category starter)"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        pen = pens[0]
        # Depth scales lightly with density; keep small for scaffold speed
        depth = max(1, min(4, int(2 + params.density)))
        cx, cy = pw / 2, ph / 2
        r = min(pw, ph) * 0.36
        # Equilateral triangle
        pts = []
        verts = []
        for k in range(3):
            ang = -math.pi / 2 + k * 2 * math.pi / 3
            verts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        for i in range(3):
            edge = _koch_edge(verts[i], verts[(i + 1) % 3], depth)
            pts.extend(edge if i == 0 else edge[1:])
        poly = Polyline(points=pts, pen_id=pen.id, closed=True)
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[make_pass("koch", "Koch outline", pen.id, [poly])],
            seed=params.seed,
            meta={"style": self.id, "category": "fractals", "scaffold": True, "depth": depth},
        )


for _e in (_KochSnowflake(),):
    register(_e)
