"""Style restylers that consume PortraitVector (not raw pixels alone)."""

from __future__ import annotations

import math

import numpy as np  # noqa: F401 — used throughout restylers

from botdraw.core.models import (
    QUALITY_LIMITS,
    LayeredSVG,
    Pen,
    Polyline,
    QualityPreset,
    StyleParams,
)
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, nearest_pen
from botdraw.portrait.models import PortraitVector
from botdraw.styles.image_utils import map_to_page


def _saturation_hex(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx <= 1e-6 else (mx - mn) / mx


def _pen_for(
    pv: PortraitVector,
    palette,
    cluster_id: str | None = None,
    rgb=None,
    *,
    respect_monochrome: bool = True,
) -> Pen:
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
        # Region ids (e.g. "r0") aren't in pv.pen_map, so this is the path
        # region-based styles (Cubism, Pen Sketch's region-outline pass)
        # actually take. On a monochrome source photo, restrict the search
        # to the palette's own low-saturation pens first — same reasoning
        # as assign_pens() in pens.py — so a B&W photo's outline regions
        # don't get quantized onto an arbitrary saturated hue. Callers that
        # need multiple distinguishable colors regardless of source chroma
        # (Cubism's facet fills, where color *is* the visual language) opt
        # out with respect_monochrome=False.
        if respect_monochrome and (pv.meta or {}).get("monochrome_source"):
            low_chroma = [p for p in pens if _saturation_hex(p.color_hex) < 0.25]
            if low_chroma:
                restricted = palette.model_copy(update={"pens": low_chroma})
                return nearest_pen(restricted, int(rgb[0]), int(rgb[1]), int(rgb[2]))
        return nearest_pen(palette, int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return pens[0]


def _budget(params: StyleParams) -> int:
    return int(QUALITY_LIMITS[params.quality]["max_paths"])


def _is_neural(pv: PortraitVector) -> bool:
    return (pv.meta or {}).get("line_source") == "neural"


def _fill_budget(pv: PortraitVector, params: StyleParams, *, edges_used: int = 0) -> int:
    """Path budget for shade/fill layers. Neural likeness lives in shade — don't starve it."""
    limit = _budget(params)
    remaining = max(0, limit - edges_used)
    if _is_neural(pv):
        return remaining
    return max(0, min(remaining, max(80, limit // 3)))


def _shade_density_map(pv: PortraitVector) -> tuple[np.ndarray, str]:
    """
    Ingest-first density map for fill styles (squiggle / stipple / tsp).

    Prefer tone_codes (neural mesh or classic mesh) over raw photo ink_target
    so stylized fills follow the same shade judgment as hatch/linework.
    Returns (HxW float [0..1], source_tag).
    """
    from PIL import Image

    if pv.tone_codes is not None:
        codes = np.asarray(pv.tone_codes, dtype=np.float32)
        # Codes 1–4 → graded density; code 5 (structure) → mid shade; 0 → empty
        dens_s = np.clip(codes / 4.0, 0.0, 1.0)
        dens_s = np.where(codes == 5, 0.55, dens_s)
        dens_s = np.where(codes == 0, 0.0, dens_s)
        dens = np.asarray(
            Image.fromarray((dens_s * 255.0).astype(np.uint8), mode="L").resize(
                (int(pv.width_px), int(pv.height_px)), Image.Resampling.NEAREST
            ),
            dtype=np.float32,
        ) / 255.0
        return dens, "tone_codes"
    arrays = pv.arrays()
    return np.asarray(arrays["ink_target"], dtype=np.float32), "ink_target"


def _ingest_first_hatch_polys(
    pv: PortraitVector,
    palette,
    *,
    limit: int,
    style: str = "hatch",
    seed: int = 1,
) -> tuple[list[Polyline], str]:
    """
    Shade polylines in ingest-first order:
    1. persisted hatch_polylines_mm
    2. rebuild from tone_codes
    3. empty (caller may fall back to classic ink_target)
    """
    hatch_src = list(pv.hatch_polylines_mm) if pv.hatch_polylines_mm else []
    if hatch_src:
        hatch_pen = _pen_for(pv, palette, "hatch") if "hatch" in pv.pen_map else _pen_for(pv, palette, "edge")
        rgb = np.asarray(pv.rgb, dtype=np.float32)
        h, w = rgb.shape[:2]
        out: list[Polyline] = []
        for pts in hatch_src:
            if len(pts) < 2:
                continue
            mx = sum(p[0] for p in pts) / len(pts)
            my = sum(p[1] for p in pts) / len(pts)
            ix = int(np.clip(mx / max(pv.page_w_mm, 1e-3) * w, 0, w - 1))
            iy = int(np.clip(my / max(pv.page_h_mm, 1e-3) * h, 0, h - 1))
            if "hatch" in pv.pen_map:
                pen = hatch_pen
            else:
                pen = _pen_for(pv, palette, rgb=rgb[iy, ix])
            out.append(Polyline(points=pts, pen_id=pen.id))
            if len(out) >= limit:
                break
        src = "mesh_walks" if pv.tone_codes is not None else "ingest_hatch"
        return out, src
    if pv.tone_codes is not None:
        return (
            _tone_grid_polys(pv, palette, limit=limit, style=style, seed=seed),
            "mesh_walks" if style == "hatch" else "mesh_walks+rebuild",
        )
    return [], "none"


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


def _tone_grid_polys(
    pv: PortraitVector,
    palette,
    *,
    limit: int,
    style: str = "hatch",
    seed: int = 1,
) -> list[Polyline]:
    """Render midtone strokes from persisted tone_codes when available."""
    if pv.tone_codes is None:
        return []
    from botdraw.portrait.tone_grid import strokes_from_tone_grid

    codes = np.asarray(pv.tone_codes, dtype=np.uint8)
    cell_px = float((pv.meta or {}).get("tone_grid", {}).get("cell_px") or 0.0)
    if cell_px <= 0:
        # Infer from grid vs image size
        gh, gw = codes.shape
        cell_px = max(4.0, float(pv.width_px) / max(gw, 1))
    # Rebuild face ROI so cached restyles keep face-priority run ordering
    try:
        from botdraw.portrait.linedraw_edges import face_roi_mask

        face = face_roi_mask(np.asarray(pv.lum, dtype=np.float32))
    except Exception:
        face = None
    strokes = strokes_from_tone_grid(
        codes,
        cell_px=cell_px,
        img_w=int(pv.width_px),
        img_h=int(pv.height_px),
        page_w=pv.page_w_mm,
        page_h=pv.page_h_mm,
        style=style,
        jitter=float((pv.meta or {}).get("linedraw_jitter") or 0.03),
        seed=seed,
        max_paths=limit,
        face=face,
    )
    hatch_pen = _pen_for(pv, palette, "hatch") if "hatch" in pv.pen_map else _pen_for(pv, palette, "edge")
    rgb = np.asarray(pv.rgb, dtype=np.float32)
    h, w = rgb.shape[:2]
    out: list[Polyline] = []
    for pts in strokes:
        if len(pts) < 2:
            continue
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        ix = int(np.clip(mx / max(pv.page_w_mm, 1e-3) * w, 0, w - 1))
        iy = int(np.clip(my / max(pv.page_h_mm, 1e-3) * h, 0, h - 1))
        if "hatch" in pv.pen_map:
            pen = hatch_pen
        else:
            pen = _pen_for(pv, palette, rgb=rgb[iy, ix])
        out.append(Polyline(points=pts, pen_id=pen.id))
        if len(out) >= limit:
            break
    return out


def _ingest_hatch_polys(pv: PortraitVector, palette, *, limit: int) -> list[Polyline]:
    """Prefer ingest hatch (tone-grid strokes); rebuild from tone_codes if needed."""
    polys, _src = _ingest_first_hatch_polys(pv, palette, limit=limit, style="hatch", seed=1)
    return polys


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
    """Primary vector style: separate Inkscape layers for structure / hatch / bands."""
    limit = _budget(params)
    edge_pen = _pen_for(pv, palette, "edge")
    edges = _edge_polys(pv, palette, limit=limit)
    hatch: list[Polyline] = []
    if include_hatch:
        hatch = _ingest_hatch_polys(pv, palette, limit=_fill_budget(pv, params, edges_used=len(edges)))
    regions: list[Polyline] = []
    if include_regions or (pv.meta or {}).get("scan_mode") == "color_bands":
        region_budget = max(0, min(80, limit // 20))
        if (pv.meta or {}).get("scan_mode") == "color_bands":
            region_budget = max(region_budget, min(160, limit // 10))
            include_regions = True
        if include_regions:
            for r in pv.regions:
                if len(regions) >= region_budget:
                    break
                mean_l = 0.299 * r.mean_rgb[0] + 0.587 * r.mean_rgb[1] + 0.114 * r.mean_rgb[2]
                if mean_l > 190 or mean_l < 25:
                    continue
                pts = list(r.points_mm)
                if not _region_outline_ok(pts, page_w=pv.page_w_mm, page_h=pv.page_h_mm):
                    continue
                pen = _pen_for(pv, palette, r.id, r.mean_rgb)
                regions.append(Polyline(points=pts, pen_id=pen.id, closed=True))

    passes = []
    if edges:
        # One structure layer (AxiDraw/Inkscape plot-by-layer friendly)
        passes.append(make_pass("structure", "1 Structure", edge_pen.id, edges, kind="ink"))
    if hatch:
        hatch_pen = _pen_for(pv, palette, "hatch") if "hatch" in pv.pen_map else edge_pen
        # Keep multi-pen hatch as sub-buckets under midtone storytelling
        buckets = _bucketize(hatch)
        if len(buckets) == 1 and hatch_pen.id in buckets:
            passes.append(make_pass("midtone", "2 Midtone hatch", hatch_pen.id, hatch, kind="ink"))
        else:
            for pid, polys in buckets.items():
                passes.append(make_pass(f"midtone-{pid}", f"2 Midtone hatch ({pid})", pid, polys, kind="ink"))
    if regions:
        for pid, polys in _bucketize(regions).items():
            passes.append(make_pass(f"bands-{pid}", f"3 Color bands ({pid})", pid, polys, kind="ink"))
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={
            "style": "portrait_linework",
            "quality": params.quality.value,
            "vector_source": "ingest",
            "inkscape_layers": [p.name for p in passes],
        },
    )


def _tone_code_at(pv: PortraitVector, x_mm: float, y_mm: float) -> int | None:
    """Look up the mesh tone-code band under a page-space point, using the
    same cell grid build_portrait_mesh laid down for this ingest."""
    codes = pv.tone_codes
    cell = float(pv.tone_cell_mm or 0.0)
    if codes is None or cell <= 0:
        return None
    codes = np.asarray(codes)
    ox, oy = pv.tone_origin_mm
    row = int((y_mm - oy) / cell)
    col = int((x_mm - ox) / cell)
    if 0 <= row < codes.shape[0] and 0 <= col < codes.shape[1]:
        return int(codes[row, col])
    return None


def _tone_band_pen_ids(pv: PortraitVector, palette) -> dict[int, str]:
    """
    Map tone-code bands (1..4, lightest to darkest shade) onto distinct
    ink pens ordered lightest-to-darkest — the multi-pen tonal shading
    "Color Shade Portrait" is named for. Without this, its ingest-first
    hatch path picked from the single ingest-assigned pen role just like
    "Hatch Portrait", making the two styles byte-identical output despite
    advertising different names.

    Respects the monochrome pen policy (see pens.py): on a low-chroma
    source, bands stay within the palette's own low-saturation pens.
    """
    candidates = ink_pens(palette) or list(palette.pens)
    if (pv.meta or {}).get("monochrome_source"):
        low_chroma = [p for p in candidates if _saturation_hex(p.color_hex) < 0.25]
        if low_chroma:
            candidates = low_chroma

    def _lum(p) -> float:
        h = p.color_hex.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return 0.299 * r + 0.587 * g + 0.114 * b

    ordered = sorted(candidates, key=_lum, reverse=True)  # lightest first
    if not ordered:
        return {}
    return {
        code: ordered[min(len(ordered) - 1, round((code - 1) / 3 * (len(ordered) - 1)))].id
        for code in range(1, 5)
    }


def restyle_hatch(
    pv: PortraitVector,
    palette,
    params: StyleParams,
    *,
    line_spacing_mm: float | None = None,
    multi_pen_bands: bool = False,
) -> LayeredSVG:
    """Prefer tone-grid / ingest hatch; fall back to midtone-masked adaptive grid.

    multi_pen_bands=True is "Color Shade Portrait": re-tags ingest hatch
    strokes by their tone-code band onto distinct pens (lightest code to
    lightest pen) instead of the single ingest-assigned hatch pen every
    other hatch-based style uses.
    """
    limit = _budget(params)
    edge_limit = max(40, limit // 8)
    edges = _edge_polys(pv, palette, limit=edge_limit)
    fill_limit = _fill_budget(pv, params, edges_used=len(edges))
    # Adaptive fallback gets the remainder of the total budget
    fallback_limit = max(fill_limit, max(0, limit - len(edges)))
    ingest, src = _ingest_first_hatch_polys(pv, palette, limit=fallback_limit, style="hatch", seed=1)
    if ingest:
        style_id = "portrait_hatch"
        if multi_pen_bands and pv.tone_codes is not None:
            band_pens = _tone_band_pen_ids(pv, palette)
            if len(set(band_pens.values())) > 1:
                retagged = []
                for poly in ingest:
                    mx, my = poly.points[len(poly.points) // 2]
                    code = _tone_code_at(pv, mx, my)
                    pen_id = band_pens.get(code) if code else None
                    retagged.append(poly.model_copy(update={"pen_id": pen_id or poly.pen_id}))
                ingest = retagged
                style_id = "portrait_color_shade"
        buckets = _bucketize(edges + ingest)
        return LayeredSVG(
            width_mm=pv.page_w_mm,
            height_mm=pv.page_h_mm,
            passes=_passes_from_buckets("hatch", "Hatch", buckets),
            seed=params.seed,
            meta={"style": style_id, "quality": params.quality.value, "vector_source": src},
        )

    # Classic adaptive fallback — only when hatch and tone_codes are both absent
    arrays = pv.arrays()
    dens, dens_src = _shade_density_map(pv)
    rgb = arrays["rgb"]
    lum = arrays["lum"]
    h, w = dens.shape
    pens = ink_pens(palette) or list(palette.pens)
    base_step = line_spacing_mm
    if base_step is None:
        base_step = max(0.6, pens[0].profile.width_mm * 2.2 / max(0.35, params.density))
    usable = min(pv.page_w_mm, pv.page_h_mm) - 20
    px_per_mm = max(w, h) / max(usable, 1)
    step = max(2, int(base_step * px_per_mm))
    lo = float(np.percentile(lum, 18))
    hi = float(np.percentile(lum, 88))
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    count = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if count >= fallback_limit:
                break
            tone = float(dens[y, x])
            lv = float(lum[y, x])
            if tone < 0.08 or (dens_src == "ink_target" and (lv < max(30.0, lo - 5) or lv > min(220.0, hi + 5))):
                continue
            pen = _pen_for(pv, palette, rgb=rgb[y, x])
            seg = max(step, int(step * (0.6 + tone)))
            x0, y0 = map_to_page(x, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
            x1, y1 = map_to_page(x + seg, y + seg, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
            buckets[pen.id].append(Polyline(points=[(x0, y0), (x1, y1)], pen_id=pen.id))
            count += 1
            if tone > 0.45 and count < fallback_limit:
                x2, y2 = map_to_page(x + seg, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
                x3, y3 = map_to_page(x, y + seg, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
                buckets[pen.id].append(Polyline(points=[(x2, y2), (x3, y3)], pen_id=pen.id))
                count += 1
        if count >= fallback_limit:
            break
    for poly in edges:
        buckets.setdefault(poly.pen_id, []).append(poly)
    fallback_src = "adaptive_fallback" if dens_src == "ink_target" else f"adaptive_{dens_src}"
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("hatch", "Hatch", buckets),
        seed=params.seed,
        meta={"style": "portrait_hatch", "quality": params.quality.value, "vector_source": fallback_src},
    )


def restyle_squiggle(pv: PortraitVector, palette, params: StyleParams, *, line_spacing_mm: float | None = None) -> LayeredSVG:
    """Squiggle fill seeded by ingest shade (tone_codes) + edge underlay."""
    arrays = pv.arrays()
    dens, dens_src = _shade_density_map(pv)
    rgb = arrays["rgb"]
    h, w = dens.shape
    pens = ink_pens(palette) or list(palette.pens)
    spacing = line_spacing_mm or max(0.8, pens[0].profile.width_mm * 2.5 / max(0.35, params.density))
    usable = min(pv.page_w_mm, pv.page_h_mm) - 20
    px_per_mm = max(w, h) / max(usable, 1)
    step_y = max(2, int(spacing * px_per_mm))
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    limit = _budget(params)
    edge_limit = max(40, limit // 6)
    fill_limit = _fill_budget(pv, params, edges_used=0)
    # Leave room for edges in the total path budget
    fill_limit = min(fill_limit if _is_neural(pv) else limit, max(0, limit - edge_limit))
    n = 0
    for y in range(0, h, step_y):
        if n >= fill_limit:
            break
        # Skip empty shade rows (tone_codes=0 or flat paper)
        if float(np.mean(dens[y, :])) < 0.04:
            continue
        pts = []
        for x in range(0, w, 2):
            tone = float(dens[y, x])
            if tone < 0.05:
                if len(pts) >= 2:
                    pen = _pen_for(pv, palette, rgb=rgb[y, min(w - 1, x)])
                    buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
                    n += 1
                    pts = []
                continue
            amp = tone * 4.0
            yy = y + math.sin(x * 0.2) * amp
            pts.append(map_to_page(x, yy, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm))
        if len(pts) >= 2 and n < fill_limit:
            pen = _pen_for(pv, palette, rgb=rgb[y, w // 2])
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
            n += 1
    for poly in _edge_polys(pv, palette, limit=edge_limit):
        buckets.setdefault(poly.pen_id, []).append(poly)
    src = f"ingest_edges+squiggle_{dens_src}"
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("sq", "Squiggle", buckets),
        seed=params.seed,
        meta={"style": "portrait_squiggle", "quality": params.quality.value, "vector_source": src},
    )


def restyle_stipple(pv: PortraitVector, palette, params: StyleParams, *, density_mul: float = 1.0) -> LayeredSVG:
    """Stipple/dots seeded by ingest shade density (tone_codes preferred)."""
    arrays = pv.arrays()
    dens, dens_src = _shade_density_map(pv)
    rgb = arrays["rgb"]
    h, w = dens.shape
    limits = QUALITY_LIMITS[params.quality]
    n = int(limits["max_dots"] * params.density * density_mul)
    if _is_neural(pv):
        # Neural shade maps are already sparse; allow fuller sampling
        n = int(n * 1.25)
    rng = np.random.default_rng(params.seed)
    pts = []
    attempts = 0
    while len(pts) < n and attempts < n * 50:
        attempts += 1
        x = int(rng.integers(0, w))
        y = int(rng.integers(0, h))
        tone = float(dens[y, x])
        if tone < 0.05:
            continue
        if rng.random() < tone:
            pts.append((x, y, tone))
    buckets: dict[str, list[Polyline]] = {}
    for x, y, tone in pts:
        pen = _pen_for(pv, palette, rgb=rgb[y, x])
        px, py = map_to_page(x, y, img_w=w, img_h=h, page_w=pv.page_w_mm, page_h=pv.page_h_mm)
        rdot = 0.15 + tone * 0.35
        circle = [
            (px + rdot * math.cos(t), py + rdot * math.sin(t))
            for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)
        ]
        buckets.setdefault(pen.id, []).append(Polyline(points=circle + [circle[0]], pen_id=pen.id, closed=True))
    edge_limit = max(40, int(QUALITY_LIMITS[params.quality]["max_paths"]) // 8)
    for poly in _edge_polys(pv, palette, limit=edge_limit):
        buckets.setdefault(poly.pen_id, []).append(poly)
    src = f"ingest_edges+stipple_{dens_src}"
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("stipple", "Stipple", buckets),
        seed=params.seed,
        meta={"style": "portrait_pointillism", "quality": params.quality.value, "vector_source": src},
    )


def _polygon_scanline_fill(
    pts: list[tuple[float, float]], step: float
) -> list[list[tuple[float, float]]]:
    """
    Horizontal scanline fill clipped to the true polygon shape.

    Replaces the previous bounding-box scanline fill, which drew every facet
    as a full-width rectangle regardless of its actual outline — the cause of
    the blocky, face-unrelated grid in Cubism renders. Returns one point list
    per fill segment (a concave/notched row can yield more than one).
    """
    from shapely.geometry import GeometryCollection, LineString, MultiLineString, Polygon

    if len(pts) < 3:
        return []
    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
    except Exception:
        return []
    if poly.is_empty or poly.bounds == ():
        return []

    minx, miny, maxx, maxy = poly.bounds
    pad = max(1.0, (maxx - minx) * 0.05)
    step = max(0.1, float(step))
    segments: list[list[tuple[float, float]]] = []
    yy = miny + step / 2.0
    while yy <= maxy:
        scan = LineString([(minx - pad, yy), (maxx + pad, yy)])
        try:
            clipped = poly.intersection(scan)
        except Exception:
            yy += step
            continue
        if clipped.is_empty:
            yy += step
            continue
        if isinstance(clipped, LineString):
            lines = [clipped]
        elif isinstance(clipped, (MultiLineString, GeometryCollection)):
            lines = [g for g in clipped.geoms if isinstance(g, LineString) and not g.is_empty]
        else:
            lines = []
        for line in lines:
            coords = list(line.coords)
            if len(coords) >= 2:
                segments.append([(float(x), float(y)) for x, y in coords])
        yy += step
    return segments


def restyle_regions_mosaic(pv: PortraitVector, palette, params: StyleParams) -> LayeredSVG:
    if not pv.regions:
        return restyle_hatch(pv, palette, params)
    outline: list[Polyline] = []
    fills: dict[str, list[Polyline]] = {}
    border = ink_pens(palette)[0] if ink_pens(palette) else palette.pens[0]
    for r in pv.regions:
        # Cubism's facets rely on multiple distinguishable colors to read
        # as facets at all; collapsing them to black on a B&W source (as
        # the outline-only regions in restyle_linework correctly do) turns
        # every facet into one continuous black fill instead. Keep full
        # palette access here.
        pen = _pen_for(pv, palette, r.id, r.mean_rgb, respect_monochrome=False)
        pts = list(r.points_mm)
        if len(pts) >= 3:
            outline.append(Polyline(points=pts, pen_id=border.id, closed=True))
        step = max(0.6, pen.profile.width_mm)
        for seg_pts in _polygon_scanline_fill(pts, step):
            fills.setdefault(pen.id, []).append(Polyline(points=seg_pts, pen_id=pen.id))
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
    # Stipple already seeds from tone_codes when available
    stippled = restyle_stipple(pv, palette, StyleParams(seed=params.seed, quality=params.quality, density=0.7), density_mul=0.7)
    dens_src = "tone_codes" if pv.tone_codes is not None else "ink_target"
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
    edge_polys = _edge_polys(pv, palette, limit=60)
    if edge_polys:
        passes.insert(0, make_pass("edges", "Portrait edges", pen.id, edge_polys))
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=passes,
        seed=params.seed,
        meta={
            "style": "portrait_tsp",
            "quality": params.quality.value,
            "vector_source": f"ingest_edges+tsp_{dens_src}",
        },
    )


def restyle_scribble_tone(pv: PortraitVector, palette, params: StyleParams, *, line_spacing_mm: float | None = None) -> LayeredSVG:
    """Scribble / hatch from tone_codes (amplitude by code) + edge underlay."""
    limit = _budget(params)
    edges = _edge_polys(pv, palette, limit=max(60, limit // 6))
    tone_budget = _fill_budget(pv, params, edges_used=len(edges))
    if not _is_neural(pv):
        tone_budget = max(200, limit - len(edges))
    tone_polys = _tone_grid_polys(
        pv,
        palette,
        limit=tone_budget,
        style="scribble",
        seed=int(params.seed) + 7,
    )
    src = "mesh_walks+edges"
    if not tone_polys:
        # Legacy fallback when tone grid missing (old caches)
        from botdraw.portrait.linedraw_edges import curve_tone_from_lum, polylines_to_mm

        arrays = pv.arrays()
        lum = arrays["lum"]
        cell = 16
        if line_spacing_mm is not None:
            cell = max(8, int(round(line_spacing_mm * 8)))
        elif params.density:
            cell = max(8, int(round(18 / max(0.5, float(params.density)))))
        curves_px = curve_tone_from_lum(
            lum.astype(np.float32),
            cell=cell,
            jitter=0.03,
            seed=int(params.seed) + 7,
            max_paths=tone_budget,
        )
        curves_mm = polylines_to_mm(
            curves_px,
            img_w=int(pv.width_px),
            img_h=int(pv.height_px),
            page_w=pv.page_w_mm,
            page_h=pv.page_h_mm,
        )
        hatch_pen = _pen_for(pv, palette, "hatch") if "hatch" in pv.pen_map else _pen_for(pv, palette, "edge")
        tone_polys = [Polyline(points=pts, pen_id=hatch_pen.id) for pts in curves_mm if len(pts) >= 2]
        src = "curve_tone+edges"
    buckets = _bucketize(edges + tone_polys[: max(0, limit - len(edges))])
    return LayeredSVG(
        width_mm=pv.page_w_mm,
        height_mm=pv.page_h_mm,
        passes=_passes_from_buckets("scribble", "Scribble tone", buckets),
        seed=params.seed,
        meta={"style": "portrait_scribble_tone", "quality": params.quality.value, "vector_source": src},
    )


RESTYLERS = {
    "portrait_linework": restyle_linework,
    "portrait_hatch": restyle_hatch,
    "portrait_color_shade": lambda pv, palette, params, **kw: restyle_hatch(
        pv, palette, params, multi_pen_bands=True, **kw
    ),
    "portrait_squiggle": restyle_squiggle,
    "portrait_pointillism": restyle_stipple,
    "portrait_dots": lambda pv, palette, params, **kw: restyle_stipple(pv, palette, params, density_mul=0.55, **kw),
    "portrait_cubism": restyle_regions_mosaic,
    "portrait_pen": restyle_pen_sketch,
    "portrait_tsp": restyle_tsp,
    "portrait_scribble_tone": restyle_scribble_tone,
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
        "portrait_scribble_tone",
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
        "line_source": (pv.meta or {}).get("line_source"),
        "line_source_warning": (pv.meta or {}).get("line_source_warning"),
    }
    return layered
