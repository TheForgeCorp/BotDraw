"""Escape-time fractal styles for GenArtBot."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import QUALITY_LIMITS, LayeredSVG, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register


def _escape_mandelbrot(cre: np.ndarray, cim: np.ndarray, max_iter: int) -> np.ndarray:
    """Iterate z <- z^2 + c; return escape iteration (max_iter if bounded)."""
    zr = np.zeros_like(cre)
    zi = np.zeros_like(cim)
    escaped = np.full(cre.shape, max_iter, dtype=np.int32)
    alive = np.ones(cre.shape, dtype=bool)
    for n in range(1, max_iter + 1):
        if not np.any(alive):
            break
        zr_a = zr[alive]
        zi_a = zi[alive]
        zr2 = zr_a * zr_a
        zi2 = zi_a * zi_a
        still = (zr2 + zi2) <= 4.0
        # Mark newly escaped among currently alive cells
        alive_coords = np.nonzero(alive)
        newly = tuple(c[~still] for c in alive_coords)
        if newly[0].size:
            escaped[newly] = n
        # Keep only still-bounded alive cells
        keep = tuple(c[still] for c in alive_coords)
        alive = np.zeros_like(alive)
        alive[keep] = True
        zr = np.zeros_like(cre)
        zi = np.zeros_like(cim)
        if keep[0].size:
            zr[keep] = zr2[still] - zi2[still] + cre[keep]
            zi[keep] = 2.0 * zr_a[still] * zi_a[still] + cim[keep]
    return escaped


class _Mandelbrot:
    id = "mandelbrot"
    name = "Mandelbrot Contours"
    category = "artistic"
    description = "Escape-time Mandelbrot bands as multicolor hatch strokes (z <- z^2 + c)"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        # image_path / image_array ignored — fractal is generative from seed
        del image_path, image_array
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        limits = QUALITY_LIMITS[params.quality]
        rng = np.random.default_rng(params.seed)

        # Resolution from quality + density
        base = int(limits["image_max"])
        w = max(80, int(base * 0.55 * params.density))
        h = max(80, int(w * (ph / pw)))
        max_iter = max(24, int(40 + base / 20 * params.density))

        # Classic window with seed-driven pan/zoom
        cx = -0.75 + float(rng.uniform(-0.35, 0.35))
        cy = float(rng.uniform(-0.25, 0.25))
        span = float(rng.uniform(1.4, 2.6))
        re0, re1 = cx - span * 0.55, cx + span * 0.45
        im0, im1 = cy - span * 0.5 * (h / w), cy + span * 0.5 * (h / w)

        xs = np.linspace(re0, re1, w, dtype=np.float64)
        ys = np.linspace(im0, im1, h, dtype=np.float64)
        cre, cim = np.meshgrid(xs, ys)
        escapes = _escape_mandelbrot(cre, cim, max_iter)

        # Map page coords: complex grid -> paper mm with margin
        margin = 8.0
        usable_w, usable_h = pw - 2 * margin, ph - 2 * margin

        def to_page(ix: float, iy: float) -> tuple[float, float]:
            return (
                margin + (ix / max(w - 1, 1)) * usable_w,
                margin + (iy / max(h - 1, 1)) * usable_h,
            )

        # Contour / hatch bands by escape iteration thresholds (exclusive iso-bands)
        n_bands = min(10, max(4, len(pens) * 2))
        mid = np.unique(
            np.clip(
                np.linspace(max(4, max_iter // 16), max_iter - 1, n_bands).astype(int),
                1,
                max_iter - 1,
            )
        )
        edges = np.unique(np.concatenate(([0], mid, [max_iter - 1])))
        row_step = max(1, int(3 / max(params.density, 0.35)))
        passes: list = []

        # Interior fill hatch (points that never escaped)
        interior_pen = pens[0]
        interior_polys: list[Polyline] = []
        for y in range(0, h, row_step * 2):
            row = escapes[y]
            run = None
            for x in range(w):
                inside = row[x] >= max_iter
                if inside and run is None:
                    run = x
                elif not inside and run is not None:
                    if x - run > 2:
                        p0 = to_page(run, y)
                        p1 = to_page(x, y)
                        interior_polys.append(Polyline(points=[p0, p1], pen_id=interior_pen.id))
                    run = None
            if run is not None and w - run > 2:
                interior_polys.append(
                    Polyline(points=[to_page(run, y), to_page(w - 1, y)], pen_id=interior_pen.id)
                )
        if interior_polys:
            passes.append(
                make_pass("mandelbrot-interior", "Mandelbrot interior", interior_pen.id, interior_polys, kind="fill")
            )

        for i in range(len(edges) - 1):
            lo, hi = int(edges[i]), int(edges[i + 1])
            if lo >= hi:
                continue
            pen = pens[(i + 1) % len(pens)]
            polys: list[Polyline] = []
            for y in range(0, h, row_step):
                row = escapes[y]
                run = None
                for x in range(w):
                    # Exclusive iso-band: lo < escape <= hi (exterior only)
                    in_band = (row[x] < max_iter) and (lo < row[x] <= hi)
                    if in_band and run is None:
                        run = x
                    elif not in_band and run is not None:
                        if x - run > 2:
                            polys.append(
                                Polyline(points=[to_page(run, y), to_page(x, y)], pen_id=pen.id)
                            )
                        run = None
                if run is not None and w - run > 2:
                    polys.append(
                        Polyline(points=[to_page(run, y), to_page(w - 1, y)], pen_id=pen.id)
                    )
            if polys:
                passes.append(
                    make_pass(f"mandelbrot-band-{i}", f"Escape {lo + 1}–{hi}", pen.id, polys)
                )

        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=passes,
            seed=params.seed,
            meta={
                "style": self.id,
                "equation": "z_{n+1} = z_n^2 + c",
                "max_iter": max_iter,
                "window": {"re": [re0, re1], "im": [im0, im1]},
            },
        )


def _hilbert_points(order: int) -> list[tuple[float, float]]:
    """Recursive Hilbert curve in unit square [0, 1]^2."""
    n = 2**order
    pts: list[tuple[float, float]] = []

    def walk(x0: float, y0: float, xi: float, xj: float, yi: float, yj: float, level: int) -> None:
        if level <= 0:
            pts.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
        else:
            walk(x0, y0, yi / 2, yj / 2, xi / 2, xj / 2, level - 1)
            walk(x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2, level - 1)
            walk(x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2, level - 1)
            walk(x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2, level - 1)

    walk(0.0, 0.0, float(n), 0.0, 0.0, float(n), order)
    # Normalize to [0, 1]
    return [(x / n, y / n) for x, y in pts]


class _HilbertCurve:
    id = "hilbert_curve"
    name = "Hilbert Curve"
    category = "artistic"
    description = "Classic space-filling Hilbert curve — single continuous black line (wall-art style)"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array  # pure generative geometry
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        pen = pens[0]  # darkest / first ink — matches framed black-line prints

        # Order 5–7: seed nudges orientation via slight margin asymmetry only
        base = {"booth-fast": 5, "booth-balanced": 6, "studio-hq": 7}[params.quality.value]
        order = int(np.clip(base + (1 if params.density >= 1.25 else 0), 4, 7))
        # Seed can drop order by 0 for reproducibility of path; use seed for rotation flip
        rng = np.random.default_rng(params.seed)
        flip_x = bool(rng.integers(0, 2))
        flip_y = bool(rng.integers(0, 2))

        unit = _hilbert_points(order)
        if flip_x:
            unit = [(1.0 - x, y) for x, y in unit]
        if flip_y:
            unit = [(x, 1.0 - y) for x, y in unit]

        # Square composition centered on page with generous mat-like margin (like the framed print)
        side = min(pw, ph) * 0.72
        ox = (pw - side) / 2
        oy = (ph - side) / 2
        page_pts = [(ox + x * side, oy + y * side) for x, y in unit]

        # Single continuous polyline — the whole fractal is one stroke
        poly = Polyline(points=page_pts, pen_id=pen.id, closed=False)
        passes = [make_pass("hilbert-curve", f"Hilbert order-{order}", pen.id, [poly])]
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=passes,
            seed=params.seed,
            meta={
                "style": self.id,
                "curve": "Hilbert",
                "order": order,
                "points": len(page_pts),
                "equation": "space-filling recursive quadrant walk",
            },
        )


for _eng in (_Mandelbrot(), _HilbertCurve()):
    register(_eng)
