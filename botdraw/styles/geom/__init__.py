"""Shared geometry helpers for D3-inspired pattern engines."""

from botdraw.styles.geom.contours import density_grid, marching_squares
from botdraw.styles.geom.delaunay import delaunay_edges, voronoi_cells
from botdraw.styles.geom.sampling import (
    poisson_disc,
    rng_from_seed,
    weighted_sites,
)
from botdraw.styles.geom.util import (
    MARK_KINDS,
    budget_take,
    circle_points,
    clip_segment,
    clip_polyline,
    hatch_rect,
    margin_box,
    mark_polyline,
    mark_polylines,
    rect_outline,
    sample_polyline,
)

__all__ = [
    "MARK_KINDS",
    "budget_take",
    "circle_points",
    "clip_polyline",
    "clip_segment",
    "delaunay_edges",
    "density_grid",
    "hatch_rect",
    "margin_box",
    "mark_polyline",
    "mark_polylines",
    "marching_squares",
    "poisson_disc",
    "rect_outline",
    "rng_from_seed",
    "sample_polyline",
    "voronoi_cells",
    "weighted_sites",
]
