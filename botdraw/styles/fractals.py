"""Fractal styles: escape-time + single-line space-filling / L-system curves."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import QUALITY_LIMITS, LayeredSVG, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register

# ---------------------------------------------------------------------------
# Escape-time Mandelbrot
# ---------------------------------------------------------------------------


def _escape_mandelbrot(cre: np.ndarray, cim: np.ndarray, max_iter: int) -> np.ndarray:
    """Iterate z <- z^2 + c; return escape iteration (max_iter if bounded)."""
    zr = np.zeros_like(cre)
    zi = np.zeros_like(cim)
    escaped = np.full(cre.shape, dtype=np.int32, fill_value=max_iter)
    alive = np.ones(cre.shape, dtype=bool)
    for n in range(1, max_iter + 1):
        if not np.any(alive):
            break
        zr_a = zr[alive]
        zi_a = zi[alive]
        zr2 = zr_a * zr_a
        zi2 = zi_a * zi_a
        still = (zr2 + zi2) <= 4.0
        alive_coords = np.nonzero(alive)
        newly = tuple(c[~still] for c in alive_coords)
        if newly[0].size:
            escaped[newly] = n
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
    category = "fractal"
    description = "Escape-time Mandelbrot bands as multicolor hatch strokes (z <- z^2 + c)"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        limits = QUALITY_LIMITS[params.quality]
        rng = np.random.default_rng(params.seed)

        base = int(limits["image_max"])
        w = max(80, int(base * 0.55 * params.density))
        h = max(80, int(w * (ph / pw)))
        max_iter = max(24, int(40 + base / 20 * params.density))

        cx = -0.75 + float(rng.uniform(-0.35, 0.35))
        cy = float(rng.uniform(-0.25, 0.25))
        span = float(rng.uniform(1.4, 2.6))
        re0, re1 = cx - span * 0.55, cx + span * 0.45
        im0, im1 = cy - span * 0.5 * (h / w), cy + span * 0.5 * (h / w)

        xs = np.linspace(re0, re1, w, dtype=np.float64)
        ys = np.linspace(im0, im1, h, dtype=np.float64)
        cre, cim = np.meshgrid(xs, ys)
        escapes = _escape_mandelbrot(cre, cim, max_iter)

        margin = 8.0
        usable_w, usable_h = pw - 2 * margin, ph - 2 * margin

        def to_page(ix: float, iy: float) -> tuple[float, float]:
            return (
                margin + (ix / max(w - 1, 1)) * usable_w,
                margin + (iy / max(h - 1, 1)) * usable_h,
            )

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
                        interior_polys.append(
                            Polyline(points=[to_page(run, y), to_page(x, y)], pen_id=interior_pen.id)
                        )
                    run = None
            if run is not None and w - run > 2:
                interior_polys.append(
                    Polyline(points=[to_page(run, y), to_page(w - 1, y)], pen_id=interior_pen.id)
                )
        if interior_polys:
            passes.append(
                make_pass(
                    "mandelbrot-interior",
                    "Mandelbrot interior",
                    interior_pen.id,
                    interior_polys,
                    kind="fill",
                )
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
                passes.append(make_pass(f"mandelbrot-band-{i}", f"Escape {lo + 1}–{hi}", pen.id, polys))

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


# ---------------------------------------------------------------------------
# Single-line helpers (L-systems + Hilbert)
# ---------------------------------------------------------------------------


def _lsystem(axiom: str, rules: dict[str, str], iters: int) -> str:
    s = axiom
    for _ in range(iters):
        s = "".join(rules.get(ch, ch) for ch in s)
    return s


def _turtle(
    cmds: str,
    *,
    step: float = 1.0,
    angle_deg: float = 90.0,
    start_heading: float = 0.0,
    forward_chars: str = "FG",
) -> list[tuple[float, float]]:
    x = y = 0.0
    heading = start_heading
    pts = [(x, y)]
    for c in cmds:
        if c in forward_chars:
            rad = math.radians(heading)
            x += step * math.cos(rad)
            y += step * math.sin(rad)
            pts.append((x, y))
        elif c == "+":
            heading += angle_deg
        elif c == "-":
            heading -= angle_deg
    return pts


def _normalize_unit(pts: list[tuple[float, float]], margin: float = 0.0) -> list[tuple[float, float]]:
    arr = np.asarray(pts, dtype=np.float64)
    mn = arr.min(axis=0)
    mx = arr.max(axis=0)
    span = np.maximum(mx - mn, 1e-9)
    scale = (1.0 - 2.0 * margin) / float(span.max())
    mid = (mn + mx) / 2.0
    return [
        (0.5 + (x - mid[0]) * scale, 0.5 + (y - mid[1]) * scale)
        for x, y in pts
    ]


def _hilbert_points(order: int) -> list[tuple[float, float]]:
    n = 2**order
    pts: list[tuple[float, float]] = []

    def walk(x0, y0, xi, xj, yi, yj, level):
        if level <= 0:
            pts.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
        else:
            walk(x0, y0, yi / 2, yj / 2, xi / 2, xj / 2, level - 1)
            walk(x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2, level - 1)
            walk(x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2, level - 1)
            walk(x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2, level - 1)

    walk(0.0, 0.0, float(n), 0.0, 0.0, float(n), order)
    return [(x / n, y / n) for x, y in pts]


def _quality_tier(quality) -> str:
    return quality.value if hasattr(quality, "value") else str(quality)


def _compose_square_stroke(
    unit_pts: list[tuple[float, float]],
    *,
    palette,
    params: StyleParams,
    paper: PaperSize,
    style_id: str,
    curve_name: str,
    pass_name: str,
    meta_extra: dict | None = None,
    fill_ratio: float = 0.72,
) -> LayeredSVG:
    pw, ph = page_size(paper)
    pen = ink_pens(palette)[0]
    rng = np.random.default_rng(params.seed)
    flip_x = bool(rng.integers(0, 2))
    flip_y = bool(rng.integers(0, 2))
    pts = unit_pts
    if flip_x:
        pts = [(1.0 - x, y) for x, y in pts]
    if flip_y:
        pts = [(x, 1.0 - y) for x, y in pts]

    side = min(pw, ph) * fill_ratio
    ox = (pw - side) / 2
    oy = (ph - side) / 2
    page_pts = [(ox + x * side, oy + y * side) for x, y in pts]
    poly = Polyline(points=page_pts, pen_id=pen.id, closed=False)
    meta = {
        "style": style_id,
        "curve": curve_name,
        "points": len(page_pts),
        "single_stroke": True,
    }
    if meta_extra:
        meta.update(meta_extra)
    return LayeredSVG(
        width_mm=pw,
        height_mm=ph,
        passes=[make_pass(f"{style_id}-stroke", pass_name, pen.id, [poly])],
        seed=params.seed,
        meta=meta,
    )


def _iters(table: dict[str, int], params: StyleParams) -> int:
    base = table[_quality_tier(params.quality)]
    bump = 1 if params.density >= 1.25 else 0
    return base + bump


# ---------------------------------------------------------------------------
# Single-line fractal engines
# ---------------------------------------------------------------------------


class _HilbertCurve:
    id = "hilbert_curve"
    name = "Hilbert Curve"
    category = "fractal"
    description = "Classic space-filling Hilbert curve — single continuous line"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 5, "booth-balanced": 6, "studio-hq": 7}, params), 4, 7))
        return _compose_square_stroke(
            _hilbert_points(order),
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Hilbert",
            pass_name=f"Hilbert order-{order}",
            meta_extra={"order": order, "equation": "space-filling recursive quadrant walk"},
        )


class _PeanoCurve:
    id = "peano"
    name = "Peano Curve"
    category = "fractal"
    description = "Space-filling Peano curve — dense woven single stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 2, "booth-balanced": 3, "studio-hq": 4}, params), 1, 4))
        s = _lsystem(
            "X",
            {
                "X": "XFYFX+F+YFXFY-F-XFYFX",
                "Y": "YFXFY-F-XFYFX+F+YFXFY",
            },
            order,
        )
        unit = _normalize_unit(_turtle(s, angle_deg=90))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Peano",
            pass_name=f"Peano order-{order}",
            meta_extra={"order": order},
        )


class _MooreCurve:
    id = "moore"
    name = "Moore Curve"
    category = "fractal"
    description = "Closed Hilbert variant — maze-like loop in one stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 3, "booth-balanced": 4, "studio-hq": 5}, params), 2, 5))
        s = _lsystem(
            "LFL+F+LFL",
            {
                "L": "-RF+LFL+FR-",
                "R": "+LF-RFR-FL+",
            },
            order,
        )
        unit = _normalize_unit(_turtle(s, angle_deg=90))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Moore",
            pass_name=f"Moore order-{order}",
            meta_extra={"order": order},
        )


class _GosperCurve:
    id = "gosper"
    name = "Gosper Curve"
    category = "fractal"
    description = "Flowsnake / Gosper curve — hexagonal single stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 2, "booth-balanced": 3, "studio-hq": 4}, params), 1, 4))
        s = _lsystem(
            "A",
            {
                "A": "A-B--B+A++AA+B-",
                "B": "+A-BB--B-A++A+B",
            },
            order,
        )
        unit = _normalize_unit(_turtle(s, angle_deg=60, forward_chars="AB"))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Gosper",
            pass_name=f"Gosper order-{order}",
            meta_extra={"order": order},
            fill_ratio=0.78,
        )


class _DragonCurve:
    id = "dragon"
    name = "Dragon Curve"
    category = "fractal"
    description = "Heighway dragon — folded ribbon in one continuous stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 9, "booth-balanced": 11, "studio-hq": 13}, params), 6, 14))
        s = _lsystem("FX", {"X": "X+YF+", "Y": "-FX-Y"}, order)
        unit = _normalize_unit(_turtle(s, angle_deg=90))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Dragon",
            pass_name=f"Dragon order-{order}",
            meta_extra={"order": order, "lsystem": "X→X+YF+ ; Y→-FX-Y"},
            fill_ratio=0.8,
        )


class _LevyC:
    id = "levy_c"
    name = "Lévy C Curve"
    category = "fractal"
    description = "Lévy C curve — self-similar C-shaped cloud stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 9, "booth-balanced": 11, "studio-hq": 13}, params), 6, 14))
        s = _lsystem("F", {"F": "+F--F+"}, order)
        unit = _normalize_unit(_turtle(s, angle_deg=45))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Lévy C",
            pass_name=f"Lévy C order-{order}",
            meta_extra={"order": order},
            fill_ratio=0.8,
        )


class _SierpinskiArrowhead:
    id = "sierpinski_arrowhead"
    name = "Sierpinski Arrowhead"
    category = "fractal"
    description = "Sierpinski arrowhead curve — triangular lace, one stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 5, "booth-balanced": 6, "studio-hq": 7}, params), 3, 8))
        s = _lsystem("XF", {"X": "YF+XF+Y", "Y": "XF-YF-X"}, order)
        unit = _normalize_unit(_turtle(s, angle_deg=60))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Sierpinski arrowhead",
            pass_name=f"Arrowhead order-{order}",
            meta_extra={"order": order},
            fill_ratio=0.78,
        )


class _KochCurve:
    id = "koch"
    name = "Koch Curve"
    category = "fractal"
    description = "Koch curve — classic snowflake edge as one open path"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 3, "booth-balanced": 4, "studio-hq": 5}, params), 2, 5))
        s = _lsystem("F", {"F": "F+F--F+F"}, order)
        unit = _normalize_unit(_turtle(s, angle_deg=60))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Koch",
            pass_name=f"Koch order-{order}",
            meta_extra={"order": order, "lsystem": "F→F+F--F+F"},
            fill_ratio=0.82,
        )


class _FibonacciWord:
    id = "fibonacci_word"
    name = "Fibonacci Word"
    category = "fractal"
    description = "Fibonacci word fractal — irregular meander from the Fib binary word"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 11, "booth-balanced": 13, "studio-hq": 15}, params), 8, 16))
        a, b = "0", "01"
        for _ in range(max(0, order - 1)):
            a, b = b, b + a
        word = b
        x = y = 0.0
        heading = 0.0
        pts = [(x, y)]
        for i, ch in enumerate(word):
            rad = math.radians(heading)
            x += math.cos(rad)
            y += math.sin(rad)
            pts.append((x, y))
            if ch == "0":
                heading += 90 if (i % 2 == 0) else -90
            else:
                heading += -90 if (i % 2 == 0) else 90
        unit = _normalize_unit(pts)
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Fibonacci word",
            pass_name=f"Fibonacci word n={order}",
            meta_extra={"order": order},
        )


class _QuadraticKoch:
    id = "quadratic_koch"
    name = "Quadratic Koch"
    category = "fractal"
    description = "Minkowski sausage / quadratic Koch — blocky shoreline stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 2, "booth-balanced": 3, "studio-hq": 4}, params), 1, 4))
        s = _lsystem("F", {"F": "F+F-F-FF+F+F-F"}, order)
        unit = _normalize_unit(_turtle(s, angle_deg=90))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Quadratic Koch",
            pass_name=f"Quadratic Koch order-{order}",
            meta_extra={"order": order},
            fill_ratio=0.8,
        )


class _Terdragon:
    id = "terdragon"
    name = "Terdragon"
    category = "fractal"
    description = "Terdragon curve — 3-fold dragon ribbon, one stroke"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        del image_path, image_array
        order = int(np.clip(_iters({"booth-fast": 6, "booth-balanced": 7, "studio-hq": 9}, params), 4, 10))
        s = _lsystem("F", {"F": "F+F-F"}, order)
        unit = _normalize_unit(_turtle(s, angle_deg=120))
        return _compose_square_stroke(
            unit,
            palette=palette,
            params=params,
            paper=paper,
            style_id=self.id,
            curve_name="Terdragon",
            pass_name=f"Terdragon order-{order}",
            meta_extra={"order": order},
            fill_ratio=0.8,
        )


for _eng in (
    _Mandelbrot(),
    _HilbertCurve(),
    _PeanoCurve(),
    _MooreCurve(),
    _GosperCurve(),
    _DragonCurve(),
    _LevyC(),
    _SierpinskiArrowhead(),
    _KochCurve(),
    _FibonacciWord(),
    _QuadraticKoch(),
    _Terdragon(),
):
    register(_eng)
