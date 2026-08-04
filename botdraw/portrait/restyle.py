"""Style restylers that consume PortraitVector (not raw pixels alone)."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import (
    QUALITY_LIMITS,
    LayeredSVG,
    PaperSize,
    Polyline,
    QualityPreset,
    StyleParams,
)
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, nearest_pen
from botdraw.portrait.models import PortraitVector
from botdraw.styles.image_utils import map_to_page


def _pen_for(pv: PortraitVector, palette, cluster_id: str | None = None, rgb=None):
    pens = ink_pens(palette) or list(palette.pens)
    if cluster_id and cluster_id in pv.pen_map:
        try:
            return palette.pen_by_id(pv.pen_map[cluster_id])
        except KeyError:
            pass
    if "edge" in pv.pen_map and cluster_id == "edge":
        try:
            return palette.pen_by_id(pv.pen_map["edge"])
        except KeyError:
            pass
    if rgb is not None:
        return nearest_pen(palette, int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return pens[0]


def restyle_linework(pv: PortraitVector, palette, params: StyleParams) -> LayeredSVG:
    edge_pen = _pen_for(pv, palette, "edge")
    polys = [
        Polyline(points=pts, pen_id=edge_pen.id)
        for pts in pv.edge_polylines_mm
        if len(pts) >= 2
    ]
    # Dark region outlines
    for r in pv.regions:
        mean_l = 0.299 * r.mean_rgb[0] + 0.587 * r.mean_rgb[1] + 0.114 * r.mean_rgb[2]
        if mean_l > 200:
            continue
        pen = _pen_for(pv, palette, r.id, r.mean_rgb)
        if len(r.points_mm) >= 2:
            polys.append(Polyline(points=list(r.points_mm), pen_id=pen.id, closed=True))
    limits = QUALITY_LIMITS[params.quality]
    polys = polys[: int(limits["max_paths"])]
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=[make_pass("edges", "Portrait edges", edge_pen.id, [p for p in polys if p.pen_id == edge_pen.id])]
        + [
            make_pass(f"reg-{pid}", f"Region {pid}", pid, [p for p in polys if p.pen_id == pid])
            for pid in {p.pen_id for p in polys if p.pen_id != edge_pen.id}
        ],
        seed=params.seed,
        meta={"style": "portrait_linework", "quality": params.quality.value},
    )


def restyle_hatch(pv: PortraitVector, palette, params: StyleParams, *, line_spacing_mm: float | None = None) -> LayeredSVG:
    arrays = pv.arrays()
    ink = arrays["ink_target"]
    rgb = arrays["rgb"]
    h, w = ink.shape
    pens = ink_pens(palette) or list(palette.pens)
    limits = QUALITY_LIMITS[params.quality]
    max_paths = int(limits["max_paths"])
    base_step = line_spacing_mm
    if base_step is None:
        base_step = max(0.6, pens[0].profile.width_mm * 2.2 / max(0.35, params.density))
    # Convert mm spacing rough → pixel step
    usable = min(pv.page_w_mm, pv.page_h_mm) - 20
    px_per_mm = max(w, h) / max(usable, 1)
    step = max(2, int(base_step * px_per_mm))
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    count = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if count >= max_paths:
                break
            tone = float(ink[y, x])
            if tone < 0.08:
                continue
            # Adaptive: darker → shorter local step via cross hatch
            pen = _pen_for(pv, palette, rgb=rgb[y, x])
            # Width-aware segment length
            seg = max(step, int(step * (0.6 + tone)))
            x0, y0 = map_to_page(x, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
            x1, y1 = map_to_page(x + seg, y + seg, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
            buckets[pen.id].append(Polyline(points=[(x0, y0), (x1, y1)], pen_id=pen.id))
            count += 1
            if tone > 0.45 and count < max_paths:
                x2, y2 = map_to_page(x + seg, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
                x3, y3 = map_to_page(x, y + seg, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
                buckets[pen.id].append(Polyline(points=[(x2, y2), (x3, y3)], pen_id=pen.id))
                count += 1
        if count >= max_paths:
            break
    passes = [make_pass(f"hatch-{pid}", f"Hatch {pid}", pid, polys) for pid, polys in buckets.items() if polys]
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_hatch", "quality": params.quality.value},
    )


def restyle_squiggle(pv: PortraitVector, palette, params: StyleParams, *, line_spacing_mm: float | None = None) -> LayeredSVG:
    arrays = pv.arrays()
    ink = arrays["ink_target"]
    rgb = arrays["rgb"]
    h, w = ink.shape
    pens = ink_pens(palette) or list(palette.pens)
    spacing = line_spacing_mm or max(0.8, pens[0].profile.width_mm * 2.5 / max(0.35, params.density))
    usable = min(pv.page_w_mm, pv.page_h_mm) - 20
    px_per_mm = max(w, h) / max(usable, 1)
    step_y = max(2, int(spacing * px_per_mm))
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    limits = QUALITY_LIMITS[params.quality]
    max_paths = int(limits["max_paths"])
    n = 0
    for y in range(0, h, step_y):
        if n >= max_paths:
            break
        pts = []
        for x in range(0, w, 2):
            amp = float(ink[y, x]) * 4.0
            yy = y + math.sin(x * 0.2) * amp
            pts.append(map_to_page(x, yy, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm))
        if len(pts) < 2:
            continue
        pen = _pen_for(pv, palette, rgb=rgb[y, w // 2])
        buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        n += 1
    passes = [make_pass(f"sq-{pid}", f"Squiggle {pid}", pid, polys) for pid, polys in buckets.items() if polys]
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_squiggle", "quality": params.quality.value},
    )


def restyle_stipple(pv: PortraitVector, palette, params: StyleParams, *, density_mul: float = 1.0) -> LayeredSVG:
    arrays = pv.arrays()
    ink = arrays["ink_target"]
    rgb = arrays["rgb"]
    h, w = ink.shape
    limits = QUALITY_LIMITS[params.quality]
    n = int(limits["max_dots"] * params.density * density_mul)
    rng = np.random.default_rng(params.seed)
    pts = []
    attempts = 0
    while len(pts) < n and attempts < n * 40:
        attempts += 1
        x = int(rng.integers(0, w))
        y = int(rng.integers(0, h))
        if rng.random() < float(ink[y, x]):
            pts.append((x, y))
    buckets: dict[str, list[Polyline]] = {}
    for x, y in pts:
        pen = _pen_for(pv, palette, rgb=rgb[y, x])
        px, py = map_to_page(x, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
        rdot = 0.15 + float(ink[y, x]) * 0.35
        circle = [
            (px + rdot * math.cos(t), py + rdot * math.sin(t))
            for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)
        ]
        buckets.setdefault(pen.id, []).append(Polyline(points=circle + [circle[0]], pen_id=pen.id, closed=True))
    passes = [make_pass(f"stipple-{pid}", f"Stipple {pid}", pid, polys) for pid, polys in buckets.items() if polys]
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_pointillism", "quality": params.quality.value},
    )


def restyle_regions_mosaic(pv: PortraitVector, palette, params: StyleParams) -> LayeredSVG:
    if not pv.regions:
        return restyle_hatch(pv, palette, params)
    outline: list[Polyline] = []
    fills: dict[str, list[Polyline]] = {}
    border = ink_pens(palette)[0] if ink_pens(palette) else palette.pens[0]
    for r in pv.regions:
        pen = _pen_for(pv, palette, r.id, r.mean_rgb)
        pts = list(r.points_mm)
        if len(pts) >= 3:
            outline.append(Polyline(points=pts, pen_id=border.id, closed=True))
        # Horizontal fill scans inside bbox
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        y0, y1 = min(ys), max(ys)
        x0, x1 = min(xs), max(xs)
        step = max(0.6, pen.profile.width_mm)
        yy = y0
        while yy <= y1:
            fills.setdefault(pen.id, []).append(Polyline(points=[(x0, yy), (x1, yy)], pen_id=pen.id))
            yy += step
    passes = [make_pass("mosaic-outline", "Facet outline", border.id, outline)]
    passes += [make_pass(f"mosaic-{pid}", f"Facet {pid}", pid, polys) for pid, polys in fills.items() if polys]
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_cubism", "quality": params.quality.value},
    )


def restyle_pen_sketch(pv: PortraitVector, palette, params: StyleParams, **kwargs) -> LayeredSVG:
    line = restyle_linework(pv, palette, params)
    hatch = restyle_hatch(pv, palette, StyleParams(seed=params.seed + 1, quality=params.quality, density=params.density * 0.6), **kwargs)
    line.passes.extend(hatch.passes)
    line.meta["style"] = "portrait_pen"
    return line


def restyle_tsp(pv: PortraitVector, palette, params: StyleParams) -> LayeredSVG:
    stippled = restyle_stipple(pv, palette, StyleParams(seed=params.seed, quality=params.quality, density=0.7), density_mul=0.7)
    centers = []
    for pas in stippled.passes:
        for poly in pas.polylines:
            if not poly.points:
                continue
            xs = [p[0] for p in poly.points]
            ys = [p[1] for p in poly.points]
            centers.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    if len(centers) < 2:
        return stippled
    remaining = centers[1:]
    tour = [centers[0]]
    while remaining:
        x, y = tour[-1]
        best_i = min(range(len(remaining)), key=lambda i: (remaining[i][0] - x) ** 2 + (remaining[i][1] - y) ** 2)
        tour.append(remaining.pop(best_i))
    pen = _pen_for(pv, palette, "edge")
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=[make_pass("tsp", "TSP path", pen.id, [Polyline(points=tour, pen_id=pen.id)])],
        seed=params.seed,
        meta={"style": "portrait_tsp", "quality": params.quality.value},
    )


RESTYLERS = {
    "portrait_linework": restyle_linework,
    "portrait_hatch": restyle_hatch,
    "portrait_color_shade": restyle_hatch,
    "portrait_squiggle": restyle_squiggle,
    "portrait_pointillism": restyle_stipple,
    "portrait_dots": lambda pv, palette, params, **kw: restyle_stipple(pv, palette, params, density_mul=0.55, **kw),
    "portrait_cubism": restyle_regions_mosaic,
    "portrait_pen": restyle_pen_sketch,
    "portrait_tsp": restyle_tsp,
}


def render_from_vector(
    style_id: str,
    pv: PortraitVector,
    palette,
    params: StyleParams,
    *,
    line_spacing_mm: float | None = None,
) -> LayeredSVG:
    fn = RESTYLERS.get(style_id)
    if fn is None:
        fn = restyle_linework
    kwargs = {}
    if line_spacing_mm is not None and style_id in (
        "portrait_hatch",
        "portrait_color_shade",
        "portrait_squiggle",
        "portrait_pen",
    ):
        kwargs["line_spacing_mm"] = line_spacing_mm
    layered = fn(pv, palette, params, **kwargs)
    layered.meta = {
        **(layered.meta or {}),
        "portrait_style": style_id,
        "ingest_id": pv.ingest_id,
        "ingest_timing_s": (pv.meta or {}).get("timing_s"),
        "pen_assignment": (pv.meta or {}).get("pen_assignment"),
        "crop": pv.crop.model_dump(),
        "quality": params.quality.value if isinstance(params.quality, QualityPreset) else params.quality,
    }
    return layered
