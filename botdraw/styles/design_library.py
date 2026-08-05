"""Design Library styles — Math Derived subsection (elementary CA, phyllotaxis, etc.)."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register
from botdraw.styles.geom import MARK_KINDS, mark_polyline

# Golden angle (degrees) — most irrational rotation; Fibonacci spiral families
GOLDEN_ANGLE_DEG = 137.5


def _extra_int(extra: dict, key: str, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    raw = extra.get(key, default)
    if raw is None:
        raw = default
    val = int(raw)
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


def _extra_float(
    extra: dict, key: str, default: float, *, lo: float | None = None, hi: float | None = None
) -> float:
    raw = extra.get(key, default)
    if raw is None:
        raw = default
    val = float(raw)
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


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
        "r = c√n, θ = n·α°; marks: circle/square/diamond/triangle/star/cross"
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
        # Points knob is authoritative; density scales mark size only
        if "n_points" in extra and extra["n_points"] is not None:
            n_points = _extra_int(extra, "n_points", 900, lo=50, hi=4000)
        elif "points" in extra and extra["points"] is not None:
            n_points = _extra_int(extra, "points", 900, lo=50, hi=4000)
        else:
            n_points = 900
        angle_deg = _extra_float(extra, "angle_deg", GOLDEN_ANGLE_DEG, lo=1.0, hi=179.0)
        mark = str(extra.get("mark") or "circle").lower().strip()
        if mark not in MARK_KINDS:
            mark = "circle"
        mark_scale = _extra_float(extra, "mark_scale", 1.0, lo=0.2, hi=4.0)
        dens = max(0.3, float(params.density or 1.0))

        # Build in polar model space with c=1, then fit to page
        raw = phyllotaxis_points(n_points, angle_deg=angle_deg, scale=1.0)
        max_r = max((math.hypot(x, y) for x, y in raw), default=1.0) or 1.0

        pw, ph = page_size(paper, orientation)
        pen = ink_pens(palette)[0]
        margin = 12.0
        usable = min(pw, ph) - 2 * margin
        page_scale = (usable * 0.5) / max_r
        cx, cy = pw / 2, ph / 2

        base_r = max(0.25, min(1.2, 7.5 / math.sqrt(n_points)))
        mark_r = base_r * dens * mark_scale
        closed = mark != "cross"
        polys: list[Polyline] = []
        for x, y in raw:
            px = cx + x * page_scale
            py = cy + y * page_scale
            pts = mark_polyline(px, py, mark_r, mark)
            if len(pts) >= 2:
                polys.append(Polyline(points=pts, pen_id=pen.id, closed=closed))

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
                "mark": mark,
                "mark_scale": mark_scale,
                "equation": f"r = c√n ; θ = n × {angle_deg}°",
                "strokes": len(polys),
            },
        )


def modular_chord_edges(n: int, k: int) -> list[tuple[int, int]]:
    """Circulant chords: for each i, edge i → (i + k) mod N (undirected, unique)."""
    n = max(3, int(n))
    k = int(k) % n
    if k == 0:
        k = 1
    # Prefer shorter step representation for uniqueness
    k = min(k, n - k) if n - k != k else k
    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for i in range(n):
        j = (i + k) % n
        a, b = (i, j) if i < j else (j, i)
        if a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        edges.append((a, b))
    return edges


class _ModularChords:
    id = "modular_chords"
    name = "Modular Chords"
    category = "design"
    description = (
        "Modular arithmetic in ink — N points on a circle, jump by k: "
        "i → (i + k) mod N; chord family forms outer petals and a dense central ring"
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
        base_n = int(extra.get("n_points") or extra.get("n") or 200)
        base_k = int(extra.get("k") or extra.get("step") or 77)
        dens = max(0.5, float(params.density or 1.0))
        n = max(12, int(round(base_n * dens)))
        k = max(1, int(base_k) % n)
        if k == 0:
            k = 1

        edges = modular_chord_edges(n, k)
        angles = [2 * math.pi * i / n for i in range(n)]

        pw, ph = page_size(paper, orientation)
        pen = ink_pens(palette)[0]
        margin = 12.0
        radius = min(pw, ph) * 0.5 - margin
        cx, cy = pw / 2, ph / 2

        def pt(i: int) -> tuple[float, float]:
            a = angles[i]
            return (cx + radius * math.cos(a), cy + radius * math.sin(a))

        polys = [Polyline(points=[pt(a), pt(b)], pen_id=pen.id) for a, b in edges]

        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[make_pass("modular-chords", f"N={n} k={k}", pen.id, polys)],
            seed=params.seed,
            meta={
                "style": self.id,
                "library": "design",
                "subsection": "math_derived",
                "n_points": n,
                "k": k,
                "equation": "i → (i + k) mod N",
                "strokes": len(polys),
            },
        )


def sieve_of_eratosthenes(n: int) -> tuple[list[bool], list[int]]:
    """Return (is_prime[0..n], primes). is_prime[0]=is_prime[1]=False."""
    n = max(2, int(n))
    is_prime = [True] * (n + 1)
    is_prime[0] = is_prime[1] = False
    p = 2
    while p * p <= n:
        if is_prime[p]:
            for m in range(p * p, n + 1, p):
                is_prime[m] = False
        p += 1
    primes = [i for i in range(2, n + 1) if is_prime[i]]
    return is_prime, primes


def _arc_points(
    x0: float, x1: float, y: float, *, steps: int = 16, above: bool = True
) -> list[tuple[float, float]]:
    """Upper (or lower) semicircle from x0→x1 sitting on baseline y."""
    if abs(x1 - x0) < 1e-6:
        return [(x0, y), (x1, y)]
    mid = (x0 + x1) / 2
    radius = abs(x1 - x0) / 2
    # Travel left→right along the arc
    if x0 <= x1:
        angles = np.linspace(math.pi, 0.0, max(4, steps))
    else:
        angles = np.linspace(0.0, math.pi, max(4, steps))
    sign = -1.0 if above else 1.0
    return [(mid + radius * math.cos(a), y + sign * radius * math.sin(a)) for a in angles]


class _PrimeSieve:
    id = "prime_sieve"
    name = "Sieve of Eratosthenes"
    category = "design"
    description = (
        "Prime sieve diptych — left: woven arc spire between successive primes; "
        "right: grid with primes circled and composites struck (cols=6 → vertical prime lanes)"
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
        base_n = int(extra.get("max_n") or extra.get("n") or 212)
        grid_cols = int(extra.get("grid_cols") or extra.get("cols") or 6)
        show_arcs = extra.get("show_arcs", True)
        show_sieve = extra.get("show_sieve", True)
        if isinstance(show_arcs, str):
            show_arcs = show_arcs.lower() not in ("0", "false", "no")
        if isinstance(show_sieve, str):
            show_sieve = show_sieve.lower() not in ("0", "false", "no")

        dens = max(0.5, float(params.density or 1.0))
        n = max(10, int(round(base_n * dens)))
        grid_cols = max(2, min(20, grid_cols))

        is_prime, primes = sieve_of_eratosthenes(n)
        pw, ph = page_size(paper, orientation)
        pen = ink_pens(palette)[0]
        margin = 12.0
        gap = 8.0
        usable_w = pw - 2 * margin
        usable_h = ph - 2 * margin

        # Diptych: arcs left, sieve right (or full-bleed if one hidden)
        if show_arcs and show_sieve:
            left_w = usable_w * 0.46
            right_w = usable_w * 0.46
            left_x0 = margin
            right_x0 = margin + left_w + gap
        elif show_arcs:
            left_w = usable_w
            right_w = 0.0
            left_x0 = margin
            right_x0 = margin
        else:
            left_w = 0.0
            right_w = usable_w
            left_x0 = margin
            right_x0 = margin

        passes: list = []
        arc_polys: list[Polyline] = []
        sieve_polys: list[Polyline] = []

        # —— Left: number line + continuous woven arc spire ——
        if show_arcs and primes:
            line_y = margin + usable_h * 0.78
            x_lo = left_x0 + 4
            x_hi = left_x0 + left_w - 4

            def map_n(v: float) -> float:
                return x_lo + (v - 1) / max(n - 1, 1) * (x_hi - x_lo)

            # Baseline
            arc_polys.append(
                Polyline(points=[(x_lo, line_y), (x_hi, line_y)], pen_id=pen.id)
            )
            # Tick marks at primes (short)
            tick = 1.6
            for p in primes:
                x = map_n(p)
                arc_polys.append(
                    Polyline(points=[(x, line_y - tick), (x, line_y + tick * 0.4)], pen_id=pen.id)
                )

            # Single continuous stroke: semicircle between consecutive primes
            path: list[tuple[float, float]] = []
            for a, b in zip(primes, primes[1:]):
                span = abs(map_n(b) - map_n(a))
                steps = max(8, min(36, int(span * 1.2)))
                seg = _arc_points(map_n(a), map_n(b), line_y, steps=steps, above=True)
                if path and seg:
                    # avoid duplicating join point
                    path.extend(seg[1:])
                else:
                    path.extend(seg)
            if len(path) >= 2:
                arc_polys.append(Polyline(points=path, pen_id=pen.id))

            # Soft outer frame for the left panel
            lx1, ly1 = left_x0, margin
            lx2, ly2 = left_x0 + left_w, margin + usable_h
            arc_polys.append(
                Polyline(
                    points=[(lx1, ly1), (lx2, ly1), (lx2, ly2), (lx1, ly2), (lx1, ly1)],
                    pen_id=pen.id,
                    closed=True,
                )
            )

        # —— Right: sieve grid ——
        if show_sieve:
            rows = int(math.ceil(n / grid_cols))
            pad = 6.0
            cell_w = (right_w - 2 * pad) / grid_cols
            cell_h = (usable_h - 2 * pad) / max(rows, 1)
            cell = min(cell_w, cell_h)
            grid_w = cell * grid_cols
            grid_h = cell * rows
            ox = right_x0 + (right_w - grid_w) / 2
            oy = margin + (usable_h - grid_h) / 2

            for num in range(1, n + 1):
                idx = num - 1
                r, c = divmod(idx, grid_cols)
                cx = ox + (c + 0.5) * cell
                cy = oy + (r + 0.5) * cell
                rad = cell * 0.32
                if num >= 2 and is_prime[num]:
                    # Circled prime
                    ring = [
                        (cx + rad * math.cos(t), cy + rad * math.sin(t))
                        for t in np.linspace(0, 2 * math.pi, 14, endpoint=False)
                    ]
                    sieve_polys.append(
                        Polyline(points=ring + [ring[0]], pen_id=pen.id, closed=True)
                    )
                elif num >= 2:
                    # Struck composite — X
                    d = rad * 0.85
                    sieve_polys.append(
                        Polyline(points=[(cx - d, cy - d), (cx + d, cy + d)], pen_id=pen.id)
                    )
                    sieve_polys.append(
                        Polyline(points=[(cx + d, cy - d), (cx - d, cy + d)], pen_id=pen.id)
                    )
                else:
                    # 1 — small dash
                    sieve_polys.append(
                        Polyline(
                            points=[(cx - rad * 0.5, cy), (cx + rad * 0.5, cy)],
                            pen_id=pen.id,
                        )
                    )

            # Light grid outline
            rx1, ry1 = ox, oy
            rx2, ry2 = ox + grid_w, oy + grid_h
            sieve_polys.append(
                Polyline(
                    points=[(rx1, ry1), (rx2, ry1), (rx2, ry2), (rx1, ry2), (rx1, ry1)],
                    pen_id=pen.id,
                    closed=True,
                )
            )

        if arc_polys:
            passes.append(make_pass("prime-arcs", "Prime arc spire", pen.id, arc_polys))
        if sieve_polys:
            passes.append(make_pass("prime-sieve", "Sieve grid", pen.id, sieve_polys))
        if not passes:
            # Fallback empty frame so render never yields zero passes
            passes.append(
                make_pass(
                    "prime-empty",
                    "Empty",
                    pen.id,
                    [
                        Polyline(
                            points=[
                                (margin, margin),
                                (pw - margin, margin),
                                (pw - margin, ph - margin),
                                (margin, ph - margin),
                                (margin, margin),
                            ],
                            pen_id=pen.id,
                            closed=True,
                        )
                    ],
                )
            )

        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=passes,
            seed=params.seed,
            meta={
                "style": self.id,
                "library": "design",
                "subsection": "math_derived",
                "max_n": n,
                "grid_cols": grid_cols,
                "prime_count": len(primes),
                "show_arcs": bool(show_arcs),
                "show_sieve": bool(show_sieve),
                "equation": "Sieve of Eratosthenes",
                "strokes": sum(len(p.polylines) for p in passes),
            },
        )


for _e in (_Rule30(), _Phyllotaxis(), _ModularChords(), _PrimeSieve()):
    register(_e)
