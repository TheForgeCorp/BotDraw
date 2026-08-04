"""Design Library styles — Math Derived subsection (elementary CA, phyllotaxis, etc.)."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register

# Golden angle (degrees) — most irrational rotation; Fibonacci spiral families
GOLDEN_ANGLE_DEG = 137.5


def evolve_cellular_automaton(
    cols: int,
    rows: int,
    *,
    rule: int = 30,
    seed_col: int | None = None,
) -> np.ndarray:
    """Evolve a 1D elementary CA (no wrap). Returns uint8 grid [rows, cols] of 0/1."""
    cols = max(3, int(cols))
    rows = max(1, int(rows))
    rule = int(rule) & 0xFF
    grid = np.zeros((rows, cols), dtype=np.uint8)
    sc = cols // 2 if seed_col is None else int(np.clip(seed_col, 0, cols - 1))
    grid[0, sc] = 1
    for y in range(1, rows):
        prev = grid[y - 1]
        for x in range(cols):
            left = int(prev[x - 1]) if x > 0 else 0
            center = int(prev[x])
            right = int(prev[x + 1]) if x + 1 < cols else 0
            idx = (left << 2) | (center << 1) | right
            grid[y, x] = 1 if ((rule >> idx) & 1) else 0
    return grid


# Alias matching the plan's test helper name
def evolve_rule30(cols: int, rows: int, rule: int = 30, seed_col: int | None = None) -> np.ndarray:
    return evolve_cellular_automaton(cols, rows, rule=rule, seed_col=seed_col)


class _Rule30:
    id = "rule30"
    name = "Rule 30"
    category = "design"
    description = (
        "Elementary cellular automaton (Wolfram Rule 30) — single-dot start; "
        "chaotic left half, striped right; classic 120×90 triangle"
    )

    def render(
        self,
        *,
        palette,
        params: StyleParams,
        paper=PaperSize.A4,
        orientation=Orientation.PORTRAIT,
        image_path=None,
        image_array=None,
    ):
        del image_path, image_array
        extra = params.extra or {}
        base_cols = int(extra.get("cols") or 120)
        base_rows = int(extra.get("rows") or 90)
        rule = int(extra.get("rule") or 30) & 0xFF
        seed_col = extra.get("seed_col")
        if seed_col is not None:
            seed_col = int(seed_col)

        # Density lightly scales resolution (keeps classic look near density=1)
        dens = max(0.5, float(params.density or 1.0))
        cols = max(16, int(round(base_cols * dens)))
        rows = max(12, int(round(base_rows * dens)))

        grid = evolve_cellular_automaton(cols, rows, rule=rule, seed_col=seed_col)

        pw, ph = page_size(paper, orientation)
        pen = ink_pens(palette)[0]
        margin = 10.0
        usable_w = max(1.0, pw - 2 * margin)
        usable_h = max(1.0, ph - 2 * margin)
        # Keep cell aspect square; center the triangle on the page
        cell = min(usable_w / cols, usable_h / rows)
        origin_x = margin + (usable_w - cell * cols) / 2
        origin_y = margin + (usable_h - cell * rows) / 2

        polys: list[Polyline] = []
        for y in range(rows):
            row = grid[y]
            run = None
            for x in range(cols):
                live = row[x] == 1
                if live and run is None:
                    run = x
                elif not live and run is not None:
                    x0 = origin_x + run * cell
                    x1 = origin_x + x * cell
                    yy = origin_y + (y + 0.5) * cell
                    if x1 - x0 >= cell * 0.25:
                        polys.append(Polyline(points=[(x0, yy), (x1, yy)], pen_id=pen.id))
                    run = None
            if run is not None:
                x0 = origin_x + run * cell
                x1 = origin_x + cols * cell
                yy = origin_y + (y + 0.5) * cell
                polys.append(Polyline(points=[(x0, yy), (x1, yy)], pen_id=pen.id))

        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[make_pass("rule30", f"Rule {rule}", pen.id, polys)],
            seed=params.seed,
            meta={
                "style": self.id,
                "library": "design",
                "subsection": "math_derived",
                "rule": rule,
                "cols": cols,
                "rows": rows,
                "seed_col": int(seed_col) if seed_col is not None else cols // 2,
                "live_cells": int(grid.sum()),
                "strokes": len(polys),
            },
        )


def phyllotaxis_points(
    n_points: int = 900,
    *,
    angle_deg: float = GOLDEN_ANGLE_DEG,
    scale: float = 1.0,
) -> list[tuple[float, float]]:
    """Vogel sunflower model: r = c√i, θ = i·α. Returns unit-disk Cartesian points."""
    n_points = max(1, int(n_points))
    alpha = math.radians(float(angle_deg))
    c = float(scale)
    pts: list[tuple[float, float]] = []
    for i in range(n_points):
        r = c * math.sqrt(i)
        th = i * alpha
        pts.append((r * math.cos(th), r * math.sin(th)))
    return pts


class _Phyllotaxis:
    id = "phyllotaxis"
    name = "Phyllotaxis"
    category = "design"
    description = (
        "Sunflower seed packing — Vogel model with golden angle 137.5°; "
        "r = c√n, θ = n·137.5°; Fibonacci spiral families (default 900 points)"
    )

    def render(
        self,
        *,
        palette,
        params: StyleParams,
        paper=PaperSize.A4,
        orientation=Orientation.PORTRAIT,
        image_path=None,
        image_array=None,
    ):
        del image_path, image_array
        extra = params.extra or {}
        base_n = int(extra.get("n_points") or extra.get("points") or 900)
        angle_deg = float(extra.get("angle_deg") or GOLDEN_ANGLE_DEG)
        dens = max(0.5, float(params.density or 1.0))
        n_points = max(50, int(round(base_n * dens)))

        # Build in polar model space with c=1, then fit to page
        raw = phyllotaxis_points(n_points, angle_deg=angle_deg, scale=1.0)
        max_r = max((math.hypot(x, y) for x, y in raw), default=1.0) or 1.0

        pw, ph = page_size(paper, orientation)
        pen = ink_pens(palette)[0]
        margin = 12.0
        usable = min(pw, ph) - 2 * margin
        page_scale = (usable * 0.5) / max_r
        cx, cy = pw / 2, ph / 2

        # Dot radius scales gently with density / count so 900 pts stay readable
        dot_r = max(0.25, min(0.85, 7.5 / math.sqrt(n_points)))
        circle_steps = 8
        polys: list[Polyline] = []
        for x, y in raw:
            px = cx + x * page_scale
            py = cy + y * page_scale
            ring = [
                (
                    px + dot_r * math.cos(t),
                    py + dot_r * math.sin(t),
                )
                for t in np.linspace(0, 2 * math.pi, circle_steps, endpoint=False)
            ]
            polys.append(Polyline(points=ring + [ring[0]], pen_id=pen.id, closed=True))

        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[make_pass("phyllotaxis", "Phyllotaxis", pen.id, polys)],
            seed=params.seed,
            meta={
                "style": self.id,
                "library": "design",
                "subsection": "math_derived",
                "n_points": n_points,
                "angle_deg": angle_deg,
                "equation": "r = c√n ; θ = n × 137.5°",
                "strokes": len(polys),
            },
        )


for _e in (_Rule30(), _Phyllotaxis()):
    register(_e)
