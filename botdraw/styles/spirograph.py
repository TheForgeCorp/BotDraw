"""Spirograph category — scaffold starter engines (expand later)."""

from __future__ import annotations

import math

from botdraw.core.models import LayeredSVG, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register


class _Hypotrochoid:
    id = "hypotrochoid"
    name = "Hypotrochoid"
    category = "spirograph"
    description = "Scaffold: classic spirograph hypotrochoid (R, r, d) curve"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        pen = pens[min(1, len(pens) - 1)]
        # Fixed ratios — enough to look like a spirograph; params later
        R, r, d = 80.0, 32.0, 48.0
        scale = min(pw, ph) * 0.0042 * (0.85 + 0.3 * params.density)
        cx, cy = pw / 2, ph / 2
        # Period for hypotrochoid: 2π * r / gcd-ish; sample densely for a clean loop
        steps = max(400, int(900 * params.density))
        turns = 5
        pts: list[tuple[float, float]] = []
        for i in range(steps * turns + 1):
            t = (i / steps) * 2 * math.pi
            x = (R - r) * math.cos(t) + d * math.cos((R - r) / r * t)
            y = (R - r) * math.sin(t) - d * math.sin((R - r) / r * t)
            pts.append((cx + x * scale, cy + y * scale))
        poly = Polyline(points=pts, pen_id=pen.id, closed=False)
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[make_pass("spiro", "Hypotrochoid", pen.id, [poly])],
            seed=params.seed,
            meta={
                "style": self.id,
                "category": "spirograph",
                "scaffold": True,
                "R": R,
                "r": r,
                "d": d,
            },
        )


for _e in (_Hypotrochoid(),):
    register(_e)
