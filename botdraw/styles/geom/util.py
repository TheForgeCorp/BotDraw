"""Clipping, outlines, and polyline budget helpers."""

from __future__ import annotations

import math
from typing import Iterable, Sequence


def margin_box(
    page_w: float, page_h: float, margin: float = 10.0
) -> tuple[float, float, float, float]:
    """Return (x0, y0, x1, y1) drawable box in mm."""
    return margin, margin, page_w - margin, page_h - margin


def budget_take(items: Sequence, max_n: int) -> list:
    if max_n <= 0:
        return []
    if len(items) <= max_n:
        return list(items)
    step = max(1, len(items) // max_n)
    out = list(items[::step])[:max_n]
    return out


def circle_points(
    cx: float, cy: float, r: float, n: int = 32, *, closed: bool = True
) -> list[tuple[float, float]]:
    n = max(3, int(n))
    pts = [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]
    if closed:
        pts.append(pts[0])
    return pts


def rect_outline(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


MARK_KINDS = ("circle", "square", "diamond", "triangle", "star", "cross")


def mark_polylines(
    cx: float,
    cy: float,
    size: float,
    kind: str = "circle",
) -> list[tuple[list[tuple[float, float]], bool]]:
    """
    Return list of (points, closed) glyphs centered at (cx, cy).

    `size` is the full outer extent in the same units as cx/cy:
    circle diameter, square side, diamond/triangle bounding box,
    star outer diameter, cross arm length.
    Cross yields two open strokes (H + V); other kinds one closed outline.
    """
    s = max(0.05, float(size))
    half = s * 0.5
    k = (kind or "circle").lower().strip()
    if k not in MARK_KINDS:
        k = "circle"

    if k == "circle":
        return [(circle_points(cx, cy, half, n=20, closed=True), True)]

    if k == "square":
        return [(rect_outline(cx - half, cy - half, cx + half, cy + half), True)]

    if k == "diamond":
        return [
            (
                [
                    (cx, cy - half),
                    (cx + half, cy),
                    (cx, cy + half),
                    (cx - half, cy),
                    (cx, cy - half),
                ],
                True,
            )
        ]

    if k == "triangle":
        # Equilateral-ish triangle with bounding width/height ≈ size
        return [
            (
                [
                    (cx, cy - half),
                    (cx + half * 0.866, cy + half * 0.5),
                    (cx - half * 0.866, cy + half * 0.5),
                    (cx, cy - half),
                ],
                True,
            )
        ]

    if k == "star":
        pts: list[tuple[float, float]] = []
        outer, inner = half, half * 0.45
        for i in range(10):
            r = outer if i % 2 == 0 else inner
            ang = -math.pi / 2 + i * math.pi / 5
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        pts.append(pts[0])
        return [(pts, True)]

    # cross — two separate strokes, no retrace; arm length = size
    return [
        ([(cx - half, cy), (cx + half, cy)], False),
        ([(cx, cy - half), (cx, cy + half)], False),
    ]


def mark_polyline(
    cx: float,
    cy: float,
    size: float,
    kind: str = "circle",
) -> list[tuple[float, float]]:
    """Single-polyline convenience wrapper (first stroke of mark_polylines)."""
    strokes = mark_polylines(cx, cy, size, kind)
    return strokes[0][0] if strokes else []


LINE_TYPES = ("solid", "dashed", "dotted", "dash_dot", "double")
# Keep dash gaps above linemerge_pass tol (0.2 mm) so dashes are not re-joined.
_MIN_DASH_GAP_MM = 0.25


def _polyline_length(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return total


def _point_at_arclength(
    points: Sequence[tuple[float, float]], dist: float
) -> tuple[float, float] | None:
    if len(points) < 2:
        return None
    remaining = max(0.0, float(dist))
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-12:
            continue
        if remaining <= seg:
            t = remaining / seg
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        remaining -= seg
    return points[-1]


def _subpath_between(
    points: Sequence[tuple[float, float]], d0: float, d1: float
) -> list[tuple[float, float]]:
    """Extract a sub-polyline from arc-length d0 to d1 along points."""
    if len(points) < 2 or d1 <= d0 + 1e-9:
        return []
    out: list[tuple[float, float]] = []
    traveled = 0.0
    started = False
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-12:
            continue
        seg_end = traveled + seg
        if seg_end < d0 - 1e-12:
            traveled = seg_end
            continue
        if not started:
            t0 = max(0.0, (d0 - traveled) / seg)
            p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            out.append(p0)
            started = True
        if seg_end >= d1 - 1e-12:
            t1 = max(0.0, min(1.0, (d1 - traveled) / seg))
            p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            if not out or abs(out[-1][0] - p1[0]) > 1e-9 or abs(out[-1][1] - p1[1]) > 1e-9:
                out.append(p1)
            break
        if not out or abs(out[-1][0] - b[0]) > 1e-9 or abs(out[-1][1] - b[1]) > 1e-9:
            out.append(b)
        traveled = seg_end
    return out if len(out) >= 2 else []


def _tangent_at(points: Sequence[tuple[float, float]], dist: float) -> tuple[float, float]:
    if len(points) < 2:
        return (1.0, 0.0)
    remaining = max(0.0, float(dist))
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg = math.hypot(dx, dy)
        if seg < 1e-12:
            continue
        if remaining <= seg:
            return (dx / seg, dy / seg)
        remaining -= seg
    a, b = points[-2], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg = math.hypot(dx, dy) or 1.0
    return (dx / seg, dy / seg)


def _offset_polyline(
    points: Sequence[tuple[float, float]], offset_mm: float
) -> list[tuple[float, float]]:
    """Simple per-vertex normal offset (open or closed)."""
    n = len(points)
    if n < 2:
        return list(points)
    closed = (
        n >= 3
        and abs(points[0][0] - points[-1][0]) < 1e-9
        and abs(points[0][1] - points[-1][1]) < 1e-9
    )
    core = points[:-1] if closed else points
    m = len(core)
    out: list[tuple[float, float]] = []
    for i in range(m):
        prev_pt = core[(i - 1) % m] if closed else core[max(0, i - 1)]
        next_pt = core[(i + 1) % m] if closed else core[min(m - 1, i + 1)]
        if not closed and i == 0:
            prev_pt = core[0]
            next_pt = core[1]
        elif not closed and i == m - 1:
            prev_pt = core[m - 2]
            next_pt = core[m - 1]
        dx, dy = next_pt[0] - prev_pt[0], next_pt[1] - prev_pt[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        out.append((core[i][0] + nx * offset_mm, core[i][1] + ny * offset_mm))
    if closed and out:
        out.append(out[0])
    return out


def stroke_linetype(
    points: Sequence[tuple[float, float]],
    *,
    linetype: str = "solid",
    density: float = 1.0,
    pattern_width_mm: float = 2.0,
    closed: bool = False,
) -> list[tuple[list[tuple[float, float]], bool]]:
    """
    Expand a path into plotter-safe polylines for the given linetype.

    Returns list of (points, closed). Gaps between dashes exceed linemerge tol.
    `density` higher → tighter repeats; `pattern_width_mm` is dash/dot length
    or double-line separation.
    """
    pts = list(points)
    if closed and len(pts) >= 2:
        if abs(pts[0][0] - pts[-1][0]) > 1e-9 or abs(pts[0][1] - pts[-1][1]) > 1e-9:
            pts = pts + [pts[0]]
    if len(pts) < 2:
        return []

    lt = (linetype or "solid").lower().strip().replace("-", "_")
    if lt not in LINE_TYPES:
        lt = "solid"
    dens = max(0.4, min(2.5, float(density)))
    width = max(0.5, min(8.0, float(pattern_width_mm)))
    total = _polyline_length(pts)

    if lt == "solid" or total < width * 0.35:
        return [(pts, bool(closed))]

    if lt == "double":
        sep = width * 0.5
        a = _offset_polyline(pts, sep)
        b = _offset_polyline(pts, -sep)
        out: list[tuple[list[tuple[float, float]], bool]] = []
        if len(a) >= 2:
            out.append((a, bool(closed)))
        if len(b) >= 2:
            out.append((b, bool(closed)))
        return out or [(pts, bool(closed))]

    gap = max(_MIN_DASH_GAP_MM, width / dens)
    strokes: list[tuple[list[tuple[float, float]], bool]] = []

    if lt == "dotted":
        spacing = max(_MIN_DASH_GAP_MM + width * 0.35, width / dens)
        tick = max(0.35, min(width, width * 0.45))
        d = 0.0
        while d <= total + 1e-9:
            p = _point_at_arclength(pts, d)
            tx, ty = _tangent_at(pts, d)
            if p is not None:
                hx, hy = -ty * tick * 0.5, tx * tick * 0.5
                strokes.append(([(p[0] - hx, p[1] - hy), (p[0] + hx, p[1] + hy)], False))
            d += spacing
        return strokes or [(pts, False)]

    # dashed / dash_dot — walk on/off along arc length
    pattern: list[tuple[bool, float]]
    if lt == "dash_dot":
        dot_len = max(0.35, width * 0.25)
        pattern = [(True, width), (False, gap), (True, dot_len), (False, gap)]
    else:
        pattern = [(True, width), (False, gap)]

    d = 0.0
    pi = 0
    while d < total - 1e-9:
        on, seg_len = pattern[pi % len(pattern)]
        pi += 1
        d1 = min(total, d + seg_len)
        if on:
            run = _subpath_between(pts, d, d1)
            if len(run) >= 2:
                strokes.append((run, False))
        d = d1
        if seg_len < 1e-9:
            break
    return strokes or [(pts, False)]


def hatch_rect(
    x0: float, y0: float, x1: float, y1: float, spacing: float
) -> list[list[tuple[float, float]]]:
    if spacing <= 0 or x1 <= x0 or y1 <= y0:
        return []
    lines: list[list[tuple[float, float]]] = []
    y = y0
    while y <= y1:
        lines.append([(x0, y), (x1, y)])
        y += spacing
    return lines


def _out_code(x: float, y: float, x0: float, y0: float, x1: float, y1: float) -> int:
    code = 0
    if x < x0:
        code |= 1
    elif x > x1:
        code |= 2
    if y < y0:
        code |= 4
    elif y > y1:
        code |= 8
    return code


def clip_segment(
    p0: tuple[float, float],
    p1: tuple[float, float],
    box: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Cohen–Sutherland clip of a segment to axis-aligned box."""
    x0, y0, x1, y1 = box
    x_a, y_a = p0
    x_b, y_b = p1
    c0 = _out_code(x_a, y_a, x0, y0, x1, y1)
    c1 = _out_code(x_b, y_b, x0, y0, x1, y1)
    while True:
        if not (c0 | c1):
            return (x_a, y_a), (x_b, y_b)
        if c0 & c1:
            return None
        code = c0 or c1
        if code & 1:
            y = y_a + (y_b - y_a) * (x0 - x_a) / (x_b - x_a + 1e-12)
            x = x0
        elif code & 2:
            y = y_a + (y_b - y_a) * (x1 - x_a) / (x_b - x_a + 1e-12)
            x = x1
        elif code & 4:
            x = x_a + (x_b - x_a) * (y0 - y_a) / (y_b - y_a + 1e-12)
            y = y0
        else:
            x = x_a + (x_b - x_a) * (y1 - y_a) / (y_b - y_a + 1e-12)
            y = y1
        if code == c0:
            x_a, y_a = x, y
            c0 = _out_code(x_a, y_a, x0, y0, x1, y1)
        else:
            x_b, y_b = x, y
            c1 = _out_code(x_b, y_b, x0, y0, x1, y1)


def clip_polyline(
    points: Sequence[tuple[float, float]],
    box: tuple[float, float, float, float],
) -> list[list[tuple[float, float]]]:
    """Clip a polyline into zero or more open runs inside box."""
    if len(points) < 2:
        return []
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for a, b in zip(points, points[1:]):
        clipped = clip_segment(a, b, box)
        if clipped is None:
            if len(current) >= 2:
                runs.append(current)
            current = []
            continue
        ca, cb = clipped
        if not current:
            current = [ca, cb]
        else:
            if abs(current[-1][0] - ca[0]) > 1e-6 or abs(current[-1][1] - ca[1]) > 1e-6:
                if len(current) >= 2:
                    runs.append(current)
                current = [ca, cb]
            else:
                current.append(cb)
    if len(current) >= 2:
        runs.append(current)
    return runs


def sample_polyline(
    points: Iterable[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    pts = list(points)
    if len(pts) <= max_points:
        return pts
    return budget_take(pts, max_points)
