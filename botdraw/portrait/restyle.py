"""Style restylers that consume PortraitVector (not raw pixels alone)."""

from __future__ import annotations

import math

import numpy as np  # noqa: F401 — used throughout restylers

from botdraw.core.models import (
    QUALITY_LIMITS,
    LayeredSVG,
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
    if "hatch" in pv.pen_map and cluster_id == "hatch":
        try:
            return palette.pen_by_id(pv.pen_map["hatch"])
        except KeyError:
            pass
    if rgb is not None:
        return nearest_pen(palette, int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return pens[0]


def _budget(params: StyleParams) -> int:
    return int(QUALITY_LIMITS[params.quality]["max_paths"])


def _edge_polys(pv: PortraitVector, palette, *, limit: int) -> list[Polyline]:
    edge_pen = _pen_for(pv, palette, "edge")
    out: list[Polyline] = []
    for pts in pv.edge_polylines_mm:
        if len(pts) < 2:
            continue
        out.append(Polyline(points=pts, pen_id=edge_pen.id))
        if len(out) >= limit:
            break
    return out


def _ingest_hatch_polys(pv: PortraitVector, palette, *, limit: int) -> list[Polyline]:
    """Use linedraw hatch from ingest when present (vectorized shading)."""
    if not pv.hatch_polylines_mm:
        return []
    hatch_pen = _pen_for(pv, palette, "hatch") if "hatch" in pv.pen_map else _pen_for(pv, palette, "edge")
    rgb = np.asarray(pv.rgb, dtype=np.float32)
    h, w = rgb.shape[:2]
    out: list[Polyline] = []
    for pts in pv.hatch_polylines_mm:
        if len(pts) < 2:
            continue
        # Sample mid-stroke color for multi-pen assignment when possible
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        # Inverse of map_to_page: rough page→px
        usable_w = pv.page_w_mm
        usable_h = pv.page_h_mm
        ix = int(np.clip(mx / max(usable_w, 1e-3) * w, 0, w - 1))
        iy = int(np.clip(my / max(usable_h, 1e-3) * h, 0, h - 1))
        pen = _pen_for(pv, palette, "hatch", rgb=rgb[iy, ix]) if "hatch" not in pv.pen_map else hatch_pen
        if "hatch" not in pv.pen_map:
            pen = _pen_for(pv, palette, rgb=rgb[iy, ix])
        out.append(Polyline(points=pts, pen_id=pen.id))
        if len(out) >= limit:
            break
    return out


def _passes_from_buckets(prefix: str, label: str, buckets: dict[str, list[Polyline]]) -> list:
    return [make_pass(f"{prefix}-{pid}", f"{label} {pid}", pid, polys) for pid, polys in buckets.items() if polys]


def _bucketize(polys: list[Polyline]) -> dict[str, list[Polyline]]:
    buckets: dict[str, list[Polyline]] = {}
    for p in polys:
        buckets.setdefault(p.pen_id, []).append(p)
    return buckets


def _region_outline_ok(pts: list[tuple[float, float]], *, page_w: float, page_h: float) -> bool:
    """Reject spiky / page-spanning vtracer outlines that ruin linework likeness."""
    if len(pts) < 4:
        return False
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bw = max(xs) - min(xs)
    bh = max(ys) - min(ys)
    if bw <= 0.5 or bh <= 0.5:
        return False
    # Spikes: long thin triangles / diagonals across the page
    diag = math.hypot(page_w, page_h)
    if math.hypot(bw, bh) > 0.45 * diag:
        return False
    # Perimeter vs bbox — very jagged closed paths often have huge perimeter
    peri = 0.0
    for i in range(1, len(pts)):
        peri += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    peri += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    box = 2.0 * (bw + bh)
    if box > 1e-3 and peri / box > 4.5:
        return False
    return True


def restyle_linework(
    pv: PortraitVector,
    palette,
    params: StyleParams,
    *,
    include_hatch: bool = True,
    include_regions: bool = False,
) -> LayeredSVG:
    """Primary vector style: linedraw edges + ingest hatch (regions off by default)."""
    limit = _budget(params)
    polys = _edge_polys(pv, palette, limit=limit)
    if include_hatch:
        # Keep hatch as supporting tone — do not drown edges
        hatch_limit = max(0, min(limit - len(polys), max(80, limit // 3)))
        polys.extend(_ingest_hatch_polys(pv, palette, limit=hatch_limit))
    if include_regions:
        # Cap region outlines — they often introduce magenta/ochre spikes
        region_budget = max(0, min(80, limit // 20))
        added = 0
        for r in pv.regions:
            if added >= region_budget or len(polys) >= limit:
                break
            mean_l = 0.299 * r.mean_rgb[0] + 0.587 * r.mean_rgb[1] + 0.114 * r.mean_rgb[2]
            if mean_l > 190 or mean_l < 25:
                continue
            pts = list(r.points_mm)
            if not _region_outline_ok(pts, page_w=pv.page_w_mm, page_h=pv.page_h_mm):
                continue
            pen = _pen_for(pv, palette, r.id, r.mean_rgb)
            polys.append(Polyline(points=pts, pen_id=pen.id, closed=True))
            added += 1

    edge_pen = _pen_for(pv, palette, "edge")
    buckets = _bucketize(polys)
    edge_pass = make_pass(
        "edges",
        "Portrait edges",
        edge_pen.id,
        buckets.pop(edge_pen.id, []),
    )
    passes = [edge_pass] if edge_pass.polylines else []
    passes += _passes_from_buckets("vec", "Vector", buckets)
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_linework", "quality": params.quality.value, "vector_source": "ingest"},
    )


def restyle_hatch(pv: PortraitVector, palette, params: StyleParams, *, line_spacing_mm: float | None = None) -> LayeredSVG:
    """Prefer linedraw ingest hatch; fall back to midtone-masked adaptive grid."""
    limit = _budget(params)
    ingest = _ingest_hatch_polys(pv, palette, limit=limit)
    if ingest:
        # Underlay edges for structure
        edges = _edge_polys(pv, palette, limit=max(40, limit // 8))
        buckets = _bucketize(edges + ingest)
        return LayeredSVG(
            width_mm=pv.page_w_mm,
            height_mm=pv.page_h_mm,
            passes=_passes_from_buckets("hatch", "Hatch", buckets),
            seed=params.seed,
            meta={"style": "portrait_hatch", "quality": params.quality.value, "vector_source": "ingest_hatch"},
        )

    arrays = pv.arrays()
    ink = arrays["ink_target"]
    rgb = arrays["rgb"]
    lum = arrays["lum"]
    h, w = ink.shape
    pens = ink_pens(palette) or list(palette.pens)
    base_step = line_spacing_mm
    if base_step is None:
        base_step = max(0.6, pens[0].profile.width_mm * 2.2 / max(0.35, params.density))
    usable = min(pv.page_w_mm, pv.page_h_mm) - 20
    px_per_mm = max(w, h) / max(usable, 1)
    step = max(2, int(base_step * px_per_mm))
    # Midtone mask: skip flat near-black backgrounds
    lo = float(np.percentile(lum, 18))
    hi = float(np.percentile(lum, 88))
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    count = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if count >= limit:
                break
            tone = float(ink[y, x])
            lv = float(lum[y, x])
            if tone < 0.08 or lv < max(30.0, lo - 5) or lv > min(220.0, hi + 5):
                continue
            pen = _pen_for(pv, palette, rgb=rgb[y, x])
            seg = max(step, int(step * (0.6 + tone)))
            x0, y0 = map_to_page(x, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
            x1, y1 = map_to_page(x + seg, y + seg, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
            buckets[pen.id].append(Polyline(points=[(x0, y0), (x1, y1)], pen_id=pen.id))
            count += 1
            if tone > 0.45 and count < limit:
                x2, y2 = map_to_page(x + seg, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
                x3, y3 = map_to_page(x, y + seg, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
                buckets[pen.id].append(Polyline(points=[(x2, y2), (x3, y3)], pen_id=pen.id))
                count += 1
        if count >= limit:
            break
    # Always add ingest edges when available
    for poly in _edge_polys(pv, palette, limit=max(40, limit // 8)):
        buckets.setdefault(poly.pen_id, []).append(poly)
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("hatch", "Hatch", buckets),
        seed=params.seed,
        meta={"style": "portrait_hatch", "quality": params.quality.value, "vector_source": "adaptive_fallback"},
    )


def restyle_squiggle(pv: PortraitVector, palette, params: StyleParams, *, line_spacing_mm: float | None = None) -> LayeredSVG:
    """Squiggle fill on midtones + linedraw edge underlay."""
    arrays = pv.arrays()
    ink = arrays["ink_target"]
    rgb = arrays["rgb"]
    lum = arrays["lum"]
    h, w = ink.shape
    pens = ink_pens(palette) or list(palette.pens)
    spacing = line_spacing_mm or max(0.8, pens[0].profile.width_mm * 2.5 / max(0.35, params.density))
    usable = min(pv.page_w_mm, pv.page_h_mm) - 20
    px_per_mm = max(w, h) / max(usable, 1)
    step_y = max(2, int(spacing * px_per_mm))
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    limit = _budget(params)
    lo = float(np.percentile(lum, 15))
    n = 0
    for y in range(0, h, step_y):
        if n >= limit:
            break
        # Skip rows that are mostly dark background
        if float(np.mean(lum[y, :])) < lo + 8:
            continue
        pts = []
        for x in range(0, w, 2):
            if float(ink[y, x]) < 0.05:
                if len(pts) >= 2:
                    pen = _pen_for(pv, palette, rgb=rgb[y, min(w - 1, x)])
                    buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
                    n += 1
                    pts = []
                continue
            amp = float(ink[y, x]) * 4.0
            yy = y + math.sin(x * 0.2) * amp
            pts.append(map_to_page(x, yy, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm))
        if len(pts) >= 2 and n < limit:
            pen = _pen_for(pv, palette, rgb=rgb[y, w // 2])
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
            n += 1
    for poly in _edge_polys(pv, palette, limit=max(40, limit // 6)):
        buckets.setdefault(poly.pen_id, []).append(poly)
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("sq", "Squiggle", buckets),
        seed=params.seed,
        meta={"style": "portrait_squiggle", "quality": params.quality.value, "vector_source": "ingest_edges+squiggle"},
    )


def restyle_stipple(pv: PortraitVector, palette, params: StyleParams, *, density_mul: float = 1.0) -> LayeredSVG:
    arrays = pv.arrays()
    ink = arrays["ink_target"]
    rgb = arrays["rgb"]
    lum = arrays["lum"]
    h, w = ink.shape
    limits = QUALITY_LIMITS[params.quality]
    n = int(limits["max_dots"] * params.density * density_mul)
    rng = np.random.default_rng(params.seed)
    lo = float(np.percentile(lum, 12))
    pts = []
    attempts = 0
    while len(pts) < n and attempts < n * 50:
        attempts += 1
        x = int(rng.integers(0, w))
        y = int(rng.integers(0, h))
        if float(lum[y, x]) < lo + 5:
            continue
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
    for poly in _edge_polys(pv, palette, limit=max(40, int(QUALITY_LIMITS[params.quality]["max_paths"]) // 8)):
        buckets.setdefault(poly.pen_id, []).append(poly)
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("stipple", "Stipple", buckets),
        seed=params.seed,
        meta={"style": "portrait_pointillism", "quality": params.quality.value, "vector_source": "ingest_edges+stipple"},
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
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        y0, y1 = min(ys), max(ys)
        x0, x1 = min(xs), max(xs)
        step = max(0.6, pen.profile.width_mm)
        yy = y0
        while yy <= y1:
            fills.setdefault(pen.id, []).append(Polyline(points=[(x0, yy), (x1, yy)], pen_id=pen.id))
            yy += step
    # Prefer ingest edges as additional outline structure
    outline.extend(_edge_polys(pv, palette, limit=80))
    passes = [make_pass("mosaic-outline", "Facet outline", border.id, outline)]
    passes += [make_pass(f"mosaic-{pid}", f"Facet {pid}", pid, polys) for pid, polys in fills.items() if polys]
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_cubism", "quality": params.quality.value, "vector_source": "regions+edges"},
    )


def restyle_pen_sketch(pv: PortraitVector, palette, params: StyleParams, **kwargs) -> LayeredSVG:
    # Edges + regions once; hatch once (ingest preferred via restyle_hatch)
    line = restyle_linework(pv, palette, params, include_hatch=False, include_regions=True)
    hatch = restyle_hatch(
        pv,
        palette,
        StyleParams(seed=params.seed + 1, quality=params.quality, density=params.density * 0.6),
        **kwargs,
    )
    # Avoid duplicating edge passes already in line
    edge_ids = {p.id for p in line.passes}
    for pas in hatch.passes:
        if pas.id.startswith("hatch-") or pas.name.startswith("Hatch"):
            # Drop pure edge-only dupes by filtering polylines already in line? Keep hatch strokes.
            line.passes.append(pas)
        elif pas.id not in edge_ids:
            line.passes.append(pas)
    line.meta["style"] = "portrait_pen"
    line.meta["vector_source"] = "ingest+hatch"
    return line


def restyle_tsp(pv: PortraitVector, palette, params: StyleParams) -> LayeredSVG:
    stippled = restyle_stipple(pv, palette, StyleParams(seed=params.seed, quality=params.quality, density=0.7), density_mul=0.7)
    centers = []
    for pas in stippled.passes:
        if pas.id.startswith("edges") or "edge" in pas.name.lower():
            continue
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
    passes = [make_pass("tsp", "TSP path", pen.id, [Polyline(points=tour, pen_id=pen.id)])]
    # Keep linedraw edges as underlay
    edge_polys = _edge_polys(pv, palette, limit=60)
    if edge_polys:
        passes.insert(0, make_pass("edges", "Portrait edges", pen.id, edge_polys))
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={"style": "portrait_tsp", "quality": params.quality.value, "vector_source": "ingest_edges+tsp"},
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
        "edge_count": len(pv.edge_polylines_mm),
        "hatch_count": len(pv.hatch_polylines_mm),
    }
    return layered
