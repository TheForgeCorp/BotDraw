"""Seeded sampling helpers: RNG, Poisson disc, image-weighted sites."""

from __future__ import annotations

import math

import numpy as np


def rng_from_seed(seed: int) -> np.random.Generator:
    return np.random.default_rng(int(seed))


def poisson_disc(
    width: float,
    height: float,
    radius: float,
    rng: np.random.Generator,
    *,
    k: int = 30,
    max_points: int = 8000,
) -> list[tuple[float, float]]:
    """Bridson Poisson-disc sampling in [0, width) × [0, height)."""
    if radius <= 0 or width <= 0 or height <= 0:
        return []
    cell = radius / math.sqrt(2)
    cols = max(1, int(math.ceil(width / cell)))
    rows = max(1, int(math.ceil(height / cell)))
    grid = [[-1] * cols for _ in range(rows)]
    points: list[tuple[float, float]] = []
    active: list[int] = []

    x0 = float(rng.uniform(0, width))
    y0 = float(rng.uniform(0, height))
    points.append((x0, y0))
    active.append(0)
    grid[int(y0 / cell)][int(x0 / cell)] = 0

    def neighbors_ok(x: float, y: float) -> bool:
        gx, gy = int(x / cell), int(y / cell)
        for yy in range(max(0, gy - 2), min(rows, gy + 3)):
            for xx in range(max(0, gx - 2), min(cols, gx + 3)):
                idx = grid[yy][xx]
                if idx < 0:
                    continue
                px, py = points[idx]
                if (px - x) ** 2 + (py - y) ** 2 < radius * radius:
                    return False
        return True

    while active and len(points) < max_points:
        ai = int(rng.integers(0, len(active)))
        i = active[ai]
        px, py = points[i]
        found = False
        for _ in range(k):
            ang = float(rng.uniform(0, 2 * math.pi))
            rad = float(rng.uniform(radius, 2 * radius))
            nx = px + rad * math.cos(ang)
            ny = py + rad * math.sin(ang)
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if not neighbors_ok(nx, ny):
                continue
            points.append((nx, ny))
            active.append(len(points) - 1)
            grid[int(ny / cell)][int(nx / cell)] = len(points) - 1
            found = True
            break
        if not found:
            active.pop(ai)
    return points


def weighted_sites(
    lum: np.ndarray,
    count: int,
    rng: np.random.Generator,
    *,
    invert: bool = True,
) -> list[tuple[float, float]]:
    """Sample sites with probability proportional to darkness (or brightness)."""
    h, w = lum.shape
    count = max(1, int(count))
    weights = (255.0 - lum) if invert else lum.astype(np.float64)
    weights = np.clip(weights, 1e-3, None).ravel()
    weights = weights / weights.sum()
    idx = rng.choice(weights.size, size=count, replace=True, p=weights)
    ys, xs = np.divmod(idx, w)
    # Jitter inside pixel
    xs = xs.astype(np.float64) + rng.random(count)
    ys = ys.astype(np.float64) + rng.random(count)
    return list(zip(xs.tolist(), ys.tolist()))
