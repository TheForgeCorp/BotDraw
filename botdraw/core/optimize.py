"""SVG path optimization wrappers (vpype when available, greedy fallback)."""

from __future__ import annotations

import math
from copy import deepcopy

from botdraw.core.models import LayeredSVG, PassLayer, Polyline


def _endpoint_dist(a: Polyline, b: Polyline) -> float:
    if not a.points or not b.points:
        return float("inf")
    return math.hypot(a.points[-1][0] - b.points[0][0], a.points[-1][1] - b.points[0][1])


def _reverse(poly: Polyline) -> Polyline:
    return Polyline(points=list(reversed(poly.points)), pen_id=poly.pen_id, closed=poly.closed)


def linesort_pass(pass_layer: PassLayer) -> PassLayer:
    """Greedy nearest-neighbor path ordering within a pass."""
    remaining = [p for p in pass_layer.polylines if len(p.points) >= 2]
    if not remaining:
        return pass_layer
    ordered: list[Polyline] = []
    current = remaining.pop(0)
    ordered.append(current)
    while remaining:
        best_i = 0
        best_d = float("inf")
        best_rev = False
        for i, cand in enumerate(remaining):
            d_fwd = _endpoint_dist(current, cand)
            d_rev = _endpoint_dist(current, _reverse(cand))
            if d_fwd < best_d:
                best_d, best_i, best_rev = d_fwd, i, False
            if d_rev < best_d:
                best_d, best_i, best_rev = d_rev, i, True
        nxt = remaining.pop(best_i)
        if best_rev and not nxt.closed:
            nxt = _reverse(nxt)
        ordered.append(nxt)
        current = nxt
    out = pass_layer.model_copy(deep=True)
    out.polylines = ordered
    return out


def linemerge_pass(pass_layer: PassLayer, tol_mm: float = 0.2) -> PassLayer:
    """Merge polylines whose endpoints nearly touch."""
    polys = [p for p in pass_layer.polylines if len(p.points) >= 2]
    if not polys:
        return pass_layer
    merged: list[Polyline] = []
    current = polys[0]
    for nxt in polys[1:]:
        if _endpoint_dist(current, nxt) <= tol_mm:
            current = Polyline(
                points=current.points + nxt.points[1:],
                pen_id=current.pen_id,
                closed=False,
            )
        else:
            merged.append(current)
            current = nxt
    merged.append(current)
    out = pass_layer.model_copy(deep=True)
    out.polylines = merged
    return out


def optimize_layered(layered: LayeredSVG, *, use_vpype: bool = True) -> LayeredSVG:
    """Optimize each pass; try vpype for SVG round-trip when installed."""
    out = deepcopy(layered)
    out.passes = [linesort_pass(linemerge_pass(p)) for p in out.passes]

    if use_vpype:
        try:
            import vpype as vp  # noqa: F401
            # Keep greedy result; vpype integration can refine file-based pipelines.
            out.meta["optimizer"] = "greedy+vpype-available"
        except Exception:
            out.meta["optimizer"] = "greedy"
    else:
        out.meta["optimizer"] = "greedy"
    return out
