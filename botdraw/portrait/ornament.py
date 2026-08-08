"""Stroke ornament: decorate centerline polylines with line types + spacing."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from botdraw.core.models import LayeredSVG, Polyline, QUALITY_LIMITS, QualityPreset


StrokeLineType = Literal[
    "solid",
    "dashed",
    "dotted",
    "dash_dot",
    "zigzag",
    "triangle",
    "wave",
    "square_wave",
    "half_circle",
    "scallop_alt",
    "beads",
    "double",
    "railroad",
    "stitch",
    "hatch_tick",
    "chevron",
    "spring",
    "bounce",
    "wobble",
    "ladder",
]

LINE_TYPES: list[str] = [
    "solid",
    "dashed",
    "dotted",
    "dash_dot",
    "zigzag",
    "triangle",
    "wave",
    "square_wave",
    "half_circle",
    "scallop_alt",
    "beads",
    "double",
    "railroad",
    "stitch",
    "hatch_tick",
    "chevron",
    "spring",
    "bounce",
    "wobble",
    "ladder",
]


class StrokeOrnamentParams(BaseModel):
    line_type: str = "solid"
    line_spacing_mm: float = 1.2
    pattern_period_mm: float = 2.0
    pattern_amplitude_mm: float = 0.8
    dash_mm: float = 2.0
    gap_mm: float = 1.2
    ornament_target: str = "all"  # all | edges | fills
    max_paths: int | None = None


def _resample(points: list[tuple[float, float]], spacing: float) -> list[tuple[float, float]]:
    if len(points) < 2:
        return list(points)
    spacing = max(0.15, spacing)
    out = [points[0]]
    acc = 0.0
    for i in range(1, len(points)):
        x0, y0 = out[-1] if acc == 0 else points[i - 1]
        # walk segment from previous original point
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9:
            continue
        ux, uy = (x1 - x0) / seg, (y1 - y0) / seg
        dist = spacing - acc
        while dist <= seg:
            out.append((x0 + ux * dist, y0 + uy * dist))
            dist += spacing
        acc = seg - (dist - spacing)
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _tangents(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    n = len(pts)
    out = []
    for i in range(n):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(dx, dy) or 1.0
        out.append((dx / L, dy / L))
    return out


def _normal(tx: float, ty: float) -> tuple[float, float]:
    return (-ty, tx)


def _dashed_chunks(
    points: list[tuple[float, float]], *, dash: float, gap: float
) -> list[list[tuple[float, float]]]:
    if len(points) < 2:
        return []
    dash = max(0.2, dash)
    gap = max(0.1, gap)
    chunks: list[list[tuple[float, float]]] = []
    drawing = True
    cur: list[tuple[float, float]] = [points[0]]
    remain = dash
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len < 1e-9:
            continue
        ux, uy = (x1 - x0) / seg_len, (y1 - y0) / seg_len
        pos = 0.0
        cx, cy = x0, y0
        while pos < seg_len:
            step = min(remain, seg_len - pos)
            nx, ny = cx + ux * step, cy + uy * step
            if drawing:
                cur.append((nx, ny))
            cx, cy = nx, ny
            pos += step
            remain -= step
            if remain <= 1e-9:
                if drawing and len(cur) >= 2:
                    chunks.append(cur)
                drawing = not drawing
                cur = [(cx, cy)] if drawing else []
                remain = dash if drawing else gap
    if drawing and len(cur) >= 2:
        chunks.append(cur)
    return chunks


def decorate_polyline(poly: Polyline, params: StrokeOrnamentParams) -> list[Polyline]:
    lt = (params.line_type or "solid").lower()
    pts = list(poly.points)
    if len(pts) < 2:
        return []
    amp = float(params.pattern_amplitude_mm)
    period = max(0.4, float(params.pattern_period_mm))
    spacing = max(0.3, float(params.line_spacing_mm))
    pen_id = poly.pen_id

    if lt == "solid":
        return [poly]

    if lt in ("dashed", "dotted", "dash_dot", "stitch"):
        dash = params.dash_mm if lt != "dotted" else min(0.4, params.dash_mm)
        gap = params.gap_mm
        if lt == "dash_dot":
            # approximate with shorter alternate dashes via smaller period chunks
            chunks = _dashed_chunks(pts, dash=dash, gap=gap * 0.5)
            extra = _dashed_chunks(pts, dash=max(0.25, dash * 0.25), gap=dash + gap)
            chunks = chunks + extra
        else:
            chunks = _dashed_chunks(pts, dash=dash, gap=gap)
        out = []
        for i, ch in enumerate(chunks):
            if lt == "stitch":
                # lateral offset alternating
                tangents = _tangents(ch) if len(ch) >= 2 else [(1.0, 0.0)]
                off = 0.25 * (1 if i % 2 == 0 else -1)
                ch = [
                    (p[0] + _normal(*tangents[min(j, len(tangents) - 1)])[0] * off,
                     p[1] + _normal(*tangents[min(j, len(tangents) - 1)])[1] * off)
                    for j, p in enumerate(ch)
                ]
            if len(ch) >= 2:
                out.append(Polyline(points=ch, pen_id=pen_id, closed=False))
        return out or [poly]

    samples = _resample(pts, period / 4)
    if len(samples) < 2:
        return [poly]
    tangents = _tangents(samples)

    def offset_wave(fn) -> list[tuple[float, float]]:
        decorated = []
        dist = 0.0
        prev = samples[0]
        for i, (x, y) in enumerate(samples):
            if i:
                dist += math.hypot(x - prev[0], y - prev[1])
            prev = (x, y)
            nx, ny = _normal(*tangents[i])
            o = fn(dist) * amp
            decorated.append((x + nx * o, y + ny * o))
        return decorated

    if lt == "zigzag":
        dec = offset_wave(lambda d: 1.0 if int(d / (period / 2)) % 2 == 0 else -1.0)
        return [Polyline(points=dec, pen_id=pen_id)]
    if lt == "triangle":
        def tri(d):
            t = (d % period) / period
            return 4 * t - 1 if t < 0.5 else 3 - 4 * t
        return [Polyline(points=offset_wave(tri), pen_id=pen_id)]
    if lt == "wave":
        return [Polyline(points=offset_wave(lambda d: math.sin(2 * math.pi * d / period)), pen_id=pen_id)]
    if lt == "square_wave":
        return [Polyline(points=offset_wave(lambda d: 1.0 if (d % period) < period / 2 else -1.0), pen_id=pen_id)]
    if lt == "wobble":
        return [Polyline(points=offset_wave(lambda d: 0.6 * math.sin(d * 0.7) + 0.4 * math.sin(d * 1.9)), pen_id=pen_id)]
    if lt == "bounce":
        def bounce(d):
            t = (d % period) / period
            return 4 * t * (1 - t)
        return [Polyline(points=offset_wave(bounce), pen_id=pen_id)]
    if lt == "spring":
        return [Polyline(points=offset_wave(lambda d: math.sin(2 * math.pi * d / max(0.3, period * 0.35))), pen_id=pen_id)]

    if lt in ("half_circle", "scallop_alt", "beads"):
        out_pts: list[tuple[float, float]] = []
        dist = 0.0
        prev = samples[0]
        side = 1
        for i, (x, y) in enumerate(samples):
            if i:
                dist += math.hypot(x - prev[0], y - prev[1])
            prev = (x, y)
            phase = (dist % period) / period
            nx, ny = _normal(*tangents[i])
            if lt == "beads":
                # circle-ish: both sides sine
                o = math.sin(phase * math.pi) * amp
                out_pts.append((x + nx * o, y + ny * o))
            else:
                s = side if lt == "scallop_alt" else 1
                o = abs(math.sin(phase * math.pi)) * amp * s
                out_pts.append((x + nx * o, y + ny * o))
                if phase < 0.02 and i > 0:
                    side *= -1
        return [Polyline(points=out_pts, pen_id=pen_id)]

    if lt == "double":
        half = spacing * 0.5
        a, b = [], []
        for i, (x, y) in enumerate(samples):
            nx, ny = _normal(*tangents[i])
            a.append((x + nx * half, y + ny * half))
            b.append((x - nx * half, y - ny * half))
        return [
            Polyline(points=a, pen_id=pen_id),
            Polyline(points=b, pen_id=pen_id),
        ]

    if lt in ("railroad", "ladder", "hatch_tick", "chevron"):
        rails = []
        if lt == "railroad":
            half = spacing * 0.45
            a, b = [], []
            for i, (x, y) in enumerate(samples):
                nx, ny = _normal(*tangents[i])
                a.append((x + nx * half, y + ny * half))
                b.append((x - nx * half, y - ny * half))
            rails = [Polyline(points=a, pen_id=pen_id), Polyline(points=b, pen_id=pen_id)]
        # ties / ticks
        ticks: list[Polyline] = []
        dist = 0.0
        prev = samples[0]
        next_at = 0.0
        for i, (x, y) in enumerate(samples):
            if i:
                dist += math.hypot(x - prev[0], y - prev[1])
            prev = (x, y)
            if dist + 1e-9 < next_at:
                continue
            next_at += period
            tx, ty = tangents[i]
            nx, ny = _normal(tx, ty)
            if lt == "chevron":
                ticks.append(
                    Polyline(
                        points=[
                            (x - tx * amp * 0.4 + nx * amp, y - ty * amp * 0.4 + ny * amp),
                            (x, y),
                            (x - tx * amp * 0.4 - nx * amp, y - ty * amp * 0.4 - ny * amp),
                        ],
                        pen_id=pen_id,
                    )
                )
            else:
                half = amp if lt != "railroad" else spacing * 0.45
                ticks.append(
                    Polyline(
                        points=[(x + nx * half, y + ny * half), (x - nx * half, y - ny * half)],
                        pen_id=pen_id,
                    )
                )
        if lt == "ladder":
            return ticks
        return rails + ticks

    return [poly]


def decorate_layered(layered: LayeredSVG, params: StrokeOrnamentParams | dict | None) -> LayeredSVG:
    if not params:
        return layered
    if isinstance(params, dict):
        params = StrokeOrnamentParams.model_validate(params)
    if (params.line_type or "solid").lower() == "solid" and params.ornament_target == "none":
        return layered

    max_paths = params.max_paths
    if max_paths is None:
        q = layered.meta.get("quality") if layered.meta else None
        try:
            max_paths = int(QUALITY_LIMITS[QualityPreset(q)]["max_paths"]) if q else 2500
        except Exception:
            max_paths = 2500

    target = (params.ornament_target or "all").lower()
    total = 0
    new_passes = []
    for pas in layered.passes:
        kind = (pas.kind or "ink").lower()
        name_l = (pas.name or "").lower()
        is_edge = "edge" in name_l or "line" in name_l or "contour" in name_l
        is_fill = "hatch" in name_l or "fill" in name_l or "shade" in name_l
        is_dot = "stipple" in name_l or "dot" in name_l or kind == "dot"
        if is_dot and target != "all":
            new_passes.append(pas)
            continue
        if target == "edges" and not is_edge:
            new_passes.append(pas)
            continue
        if target == "fills" and not is_fill and is_edge:
            new_passes.append(pas)
            continue

        new_polys: list[Polyline] = []
        for poly in pas.polylines:
            if total >= max_paths:
                break
            decorated = decorate_polyline(poly, params)
            for d in decorated:
                if total >= max_paths:
                    break
                new_polys.append(d)
                total += 1
        # Never fall back to the undecorated pass: new_polys already IS the
        # budget-capped result (possibly empty, when an earlier pass already
        # exhausted max_paths). Falling back to pas.polylines here used to
        # silently restore the full, un-budgeted pass whenever a pass hit
        # the cap on its very first polyline — the ~20% path-budget
        # overshoot measured with non-solid line types (ladder/dotted).
        new_passes.append(pas.model_copy(update={"polylines": new_polys}))

    # optimize_layered() reads the flat meta["linetype"] key to decide
    # whether vpype's merge() is safe to run (it glues dash/dot gaps back
    # together, since it only sees geometry, not intent). Previously this
    # was only ever written nested at meta["ornament"]["line_type"], which
    # optimize_layered never reads — so non-solid line types silently went
    # through vpype merge and could have their gaps re-glued.
    meta = {
        **(layered.meta or {}),
        "ornament": params.model_dump(),
        "linetype": params.line_type or "solid",
    }
    return layered.model_copy(update={"passes": new_passes, "meta": meta})
