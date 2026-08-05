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
