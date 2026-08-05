"""Marching-squares isolines and simple density fields."""

from __future__ import annotations

import math

import numpy as np


# Edge midpoints relative to cell (i,j) → (i+1,j+1): bottom, right, top, left
# Segments keyed by case 0..15
_SEGMENTS: dict[int, list[tuple[int, int]]] = {
    1: [(3, 0)],
    2: [(0, 1)],
    3: [(3, 1)],
    4: [(1, 2)],
    5: [(3, 2), (0, 1)],  # saddle — simple split
    6: [(0, 2)],
    7: [(3, 2)],
    8: [(2, 3)],
    9: [(0, 2)],
    10: [(0, 3), (1, 2)],
    11: [(1, 2)],
    12: [(1, 3)],
    13: [(0, 1)],
    14: [(0, 3)],
}


def _edge_point(
    edge: int,
    i: int,
    j: int,
    values: np.ndarray,
    level: float,
    x_scale: float,
    y_scale: float,
    x0: float,
    y0: float,
) -> tuple[float, float]:
    """Interpolate point on cell edge in world coords. i=col, j=row."""
    # Corners: 0=(i,j), 1=(i+1,j), 2=(i+1,j+1), 3=(i,j+1) — row increases down
    v00 = float(values[j, i])
    v10 = float(values[j, i + 1])
    v11 = float(values[j + 1, i + 1])
    v01 = float(values[j + 1, i])

    def lerp(a: float, b: float, va: float, vb: float) -> float:
        if abs(vb - va) < 1e-12:
            return 0.5
        return (level - va) / (vb - va)

    if edge == 0:  # bottom j
        t = lerp(0, 1, v00, v10)
        return x0 + (i + t) * x_scale, y0 + j * y_scale
    if edge == 1:  # right i+1
        t = lerp(0, 1, v10, v11)
        return x0 + (i + 1) * x_scale, y0 + (j + t) * y_scale
    if edge == 2:  # top j+1
        t = lerp(0, 1, v01, v11)
        return x0 + (i + t) * x_scale, y0 + (j + 1) * y_scale
    # edge 3 left i
    t = lerp(0, 1, v00, v01)
    return x0 + i * x_scale, y0 + (j + t) * y_scale


def marching_squares(
    values: np.ndarray,
    levels: list[float] | np.ndarray,
    *,
    x0: float = 0.0,
    y0: float = 0.0,
    x_scale: float = 1.0,
    y_scale: float = 1.0,
) -> list[tuple[float, list[list[tuple[float, float]]]]]:
    """
    Extract open segment chains per level.

    values: 2D array (rows, cols). Returns [(level, [polylines])].
    """
    h, w = values.shape
    if h < 2 or w < 2:
        return []
    out: list[tuple[float, list[list[tuple[float, float]]]]] = []
    for level in levels:
        segs: list[list[tuple[float, float]]] = []
        for j in range(h - 1):
            for i in range(w - 1):
                tl = 1 if values[j, i] >= level else 0
                tr = 1 if values[j, i + 1] >= level else 0
                br = 1 if values[j + 1, i + 1] >= level else 0
                bl = 1 if values[j + 1, i] >= level else 0
                case = (tl << 3) | (tr << 2) | (br << 1) | bl
                for e0, e1 in _SEGMENTS.get(case, []):
                    p0 = _edge_point(e0, i, j, values, level, x_scale, y_scale, x0, y0)
                    p1 = _edge_point(e1, i, j, values, level, x_scale, y_scale, x0, y0)
                    segs.append([p0, p1])
        chains = _stitch(segs)
        if chains:
            out.append((float(level), chains))
    return out


def _stitch(
    segs: list[list[tuple[float, float]]], tol: float = 1e-4
) -> list[list[tuple[float, float]]]:
    if not segs:
        return []
    unused = list(segs)
    chains: list[list[tuple[float, float]]] = []

    def near(a: tuple[float, float], b: tuple[float, float]) -> bool:
        return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    while unused:
        chain = list(unused.pop())
        changed = True
        while changed:
            changed = False
            for k in range(len(unused) - 1, -1, -1):
                s = unused[k]
                if near(chain[-1], s[0]):
                    chain.extend(s[1:])
                    unused.pop(k)
                    changed = True
                elif near(chain[-1], s[-1]):
                    chain.extend(reversed(s[:-1]))
                    unused.pop(k)
                    changed = True
                elif near(chain[0], s[-1]):
                    chain = s[:-1] + chain
                    unused.pop(k)
                    changed = True
                elif near(chain[0], s[0]):
                    chain = list(reversed(s[1:])) + chain
                    unused.pop(k)
                    changed = True
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def density_grid(
    points: list[tuple[float, float]],
    width: float,
    height: float,
    *,
    cols: int = 64,
    rows: int = 64,
    sigma: float | None = None,
) -> tuple[np.ndarray, float, float]:
    """
    Build a smooth density field from point samples via binned blur.

    Returns (grid, x_scale, y_scale) covering [0,width]×[0,height].
    """
    cols = max(8, int(cols))
    rows = max(8, int(rows))
    grid = np.zeros((rows, cols), dtype=np.float64)
    if not points:
        return grid, width / max(cols - 1, 1), height / max(rows - 1, 1)
    for x, y in points:
        c = int(np.clip(x / width * (cols - 1), 0, cols - 1))
        r = int(np.clip(y / height * (rows - 1), 0, rows - 1))
        grid[r, c] += 1.0
    # Box blur as cheap KDE stand-in
    rad = max(1, int(sigma if sigma is not None else max(cols, rows) * 0.04))
    kernel = np.ones((2 * rad + 1, 2 * rad + 1), dtype=np.float64)
    kernel /= kernel.sum()
    # pad + convolve via FFT-free nested loops on small grids
    padded = np.pad(grid, rad, mode="edge")
    out = np.zeros_like(grid)
    for j in range(rows):
        for i in range(cols):
            out[j, i] = (padded[j : j + 2 * rad + 1, i : i + 2 * rad + 1] * kernel).sum()
    x_scale = width / max(cols - 1, 1)
    y_scale = height / max(rows - 1, 1)
    return out, x_scale, y_scale
