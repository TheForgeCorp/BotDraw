"""Compact Bowyer–Watson Delaunay + Voronoi cell edges (no scipy)."""

from __future__ import annotations

import math
from collections import defaultdict


def _circumcircle(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> tuple[float, float, float] | None:
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ax2 = ax * ax + ay * ay
    bx2 = bx * bx + by * by
    cx2 = cx * cx + cy * cy
    ux = (ax2 * (by - cy) + bx2 * (cy - ay) + cx2 * (ay - by)) / d
    uy = (ax2 * (cx - bx) + bx2 * (ax - cx) + cx2 * (bx - ax)) / d
    r2 = (ux - ax) ** 2 + (uy - ay) ** 2
    return ux, uy, r2


def delaunay_triangulation(
    points: list[tuple[float, float]],
) -> list[tuple[int, int, int]]:
    """Return list of triangles as index triples into points."""
    n = len(points)
    if n < 3:
        return []

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    dx = max(max_x - min_x, 1.0)
    dy = max(max_y - min_y, 1.0)
    delta = max(dx, dy) * 10
    mid_x = (min_x + max_x) / 2
    mid_y = (min_y + max_y) / 2

    # Super-triangle vertices appended
    p_st = [
        (mid_x - 2 * delta, mid_y - delta),
        (mid_x, mid_y + 2 * delta),
        (mid_x + 2 * delta, mid_y - delta),
    ]
    pts = list(points) + p_st
    st_i = (n, n + 1, n + 2)
    triangles: list[tuple[int, int, int]] = [st_i]

    for i in range(n):
        pi = pts[i]
        bad: list[tuple[int, int, int]] = []
        for tri in triangles:
            circ = _circumcircle(pts[tri[0]], pts[tri[1]], pts[tri[2]])
            if circ is None:
                continue
            cx, cy, r2 = circ
            if (pi[0] - cx) ** 2 + (pi[1] - cy) ** 2 <= r2 * (1 + 1e-10):
                bad.append(tri)
        edge_count: dict[tuple[int, int], int] = defaultdict(int)
        for tri in bad:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                e = (a, b) if a < b else (b, a)
                edge_count[e] += 1
        triangles = [t for t in triangles if t not in bad]
        for (a, b), cnt in edge_count.items():
            if cnt == 1:
                triangles.append((a, b, i))

    # Drop triangles that touch super-triangle
    st_set = set(st_i)
    return [t for t in triangles if not (set(t) & st_set)]


def delaunay_edges(
    points: list[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    tris = delaunay_triangulation(points)
    seen: set[tuple[int, int]] = set()
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            e = (u, v) if u < v else (v, u)
            if e in seen:
                continue
            seen.add(e)
            edges.append((points[e[0]], points[e[1]]))
    return edges


def voronoi_cells(
    points: list[tuple[float, float]],
    bounds: tuple[float, float, float, float],
) -> list[list[tuple[float, float]]]:
    """
    Approximate Voronoi cell outlines from Delaunay dual.

    Returns closed polylines (may be clipped roughly to bounds).
    Cells with too few vertices are skipped.
    """
    if len(points) < 3:
        return []
    tris = delaunay_triangulation(points)
    if not tris:
        return []

    # Circumcenter per triangle
    centers: list[tuple[float, float] | None] = []
    for a, b, c in tris:
        circ = _circumcircle(points[a], points[b], points[c])
        centers.append((circ[0], circ[1]) if circ else None)

    # Map undirected edge -> list of triangle indices sharing it
    edge_tris: dict[tuple[int, int], list[int]] = defaultdict(list)
    for ti, (a, b, c) in enumerate(tris):
        for u, v in ((a, b), (b, c), (c, a)):
            e = (u, v) if u < v else (v, u)
            edge_tris[e].append(ti)

    # For each site, collect Voronoi vertices (circumcenters of incident tris)
    site_verts: list[list[tuple[float, float]]] = [[] for _ in points]
    for ti, (a, b, c) in enumerate(tris):
        ctr = centers[ti]
        if ctr is None:
            continue
        for s in (a, b, c):
            site_verts[s].append(ctr)

    x0, y0, x1, y1 = bounds
    cells: list[list[tuple[float, float]]] = []
    for verts in site_verts:
        if len(verts) < 3:
            continue
        # Order by angle around centroid
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        ordered = sorted(verts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        # Dedup nearly identical
        unique: list[tuple[float, float]] = []
        for p in ordered:
            if not unique or (p[0] - unique[-1][0]) ** 2 + (p[1] - unique[-1][1]) ** 2 > 1e-8:
                unique.append(p)
        if len(unique) < 3:
            continue
        # Clip vertices loosely into expanded bounds (keep connectivity)
        clipped = [
            (min(max(p[0], x0), x1), min(max(p[1], y0), y1)) for p in unique
        ]
        clipped.append(clipped[0])
        cells.append(clipped)
    return cells
