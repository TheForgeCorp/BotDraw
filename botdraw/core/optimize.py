"""SVG path optimization wrappers (vpype when available, greedy fallback)."""

from __future__ import annotations

import math
from copy import deepcopy

import numpy as np

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


def _vpype_optimize_pass(pass_layer: PassLayer, *, tol_mm: float = 0.2) -> PassLayer | None:
    """
    Run vpype LineCollection.merge + LineIndex linesort (mm units).

    Returns None if vpype is unavailable or the pass cannot be converted.
    """
    try:
        import vpype as vp
    except Exception:
        return None
    polys = [p for p in pass_layer.polylines if len(p.points) >= 2]
    if not polys:
        return pass_layer
    # Preserve pen_id / closed via parallel metadata (vpype is geometry-only)
    lc = vp.LineCollection()
    meta: list[tuple[str, bool]] = []
    for p in polys:
        arr = np.asarray([complex(float(x), float(y)) for x, y in p.points], dtype=np.complex128)
        lc.append(arr)
        meta.append((p.pen_id, bool(p.closed)))
    try:
        lc.merge(tolerance=float(tol_mm), flip=True)
        if len(lc) >= 2:
            line_index = vp.LineIndex(lc[1:], reverse=True)
            new_lines = lc.clone([lc[0]])
            while len(line_index) > 0:
                idx, reverse = line_index.find_nearest(new_lines[-1][-1])
                line = line_index.pop(idx)
                if line is None:
                    continue
                if reverse:
                    line = np.flip(line)
                new_lines.append(line)
            lc = new_lines
    except Exception:
        return None

    # After merge, path count/order no longer matches meta 1:1 — use pass pen_id
    pen_id = pass_layer.pen_id
    out_polys: list[Polyline] = []
    for line in lc:
        if line is None or len(line) < 2:
            continue
        pts = [(float(c.real), float(c.imag)) for c in np.asarray(line)]
        out_polys.append(Polyline(points=pts, pen_id=pen_id, closed=False))
    out = pass_layer.model_copy(deep=True)
    out.polylines = out_polys
    return out


def optimize_layered(layered: LayeredSVG, *, use_vpype: bool = True) -> LayeredSVG:
    """Optimize each pass; use vpype merge/sort when installed, else greedy."""
    out = deepcopy(layered)
    linetype = str((out.meta or {}).get("linetype") or "solid")
    if linetype != "solid":
        # Dashed/dotted patterns must keep segment count — vpype merge glues dash gaps.
        out.passes = [linesort_pass(p) for p in out.passes]
        out.meta["optimizer"] = "greedy-linetype"
        return out
    used_vpype = False
    if use_vpype:
        try:
            import vpype as vp  # noqa: F401

            new_passes: list[PassLayer] = []
            for p in out.passes:
                optimized = _vpype_optimize_pass(p, tol_mm=0.2)
                if optimized is None:
                    new_passes.append(linesort_pass(linemerge_pass(p)))
                else:
                    used_vpype = True
                    new_passes.append(optimized)
            out.passes = new_passes
            out.meta["optimizer"] = "vpype" if used_vpype else "greedy"
            return out
        except Exception:
            pass

    out.passes = [linesort_pass(linemerge_pass(p)) for p in out.passes]
    out.meta["optimizer"] = "greedy"
    return out
