"""D3-inspired pattern StyleEngines (Python/NumPy polylines)."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import QUALITY_LIMITS, LayeredSVG, Orientation, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, nearest_pen
from botdraw.styles import page_size, register
from botdraw.styles.geom import (
    budget_take,
    circle_points,
    clip_polyline,
    clip_segment,
    delaunay_edges,
    density_grid,
    hatch_rect,
    margin_box,
    marching_squares,
    poisson_disc,
    rect_outline,
    rng_from_seed,
    voronoi_cells,
    weighted_sites,
)
from botdraw.styles.image_utils import luminance, load_image_array, map_to_page, synthetic_portrait


def _img(params: StyleParams, image_path, image_array):
    limits = QUALITY_LIMITS[params.quality]
    if image_array is not None:
        return image_array
    if image_path:
        return load_image_array(image_path, int(limits["image_max"]))
    return synthetic_portrait(int(limits["image_max"]))


def _page_ctx(paper, orientation, margin: float = 10.0):
    pw, ph = page_size(paper, orientation)
    box = margin_box(pw, ph, margin)
    return pw, ph, box


def _site_count(params: StyleParams, base: int = 80) -> int:
    limits = QUALITY_LIMITS[params.quality]
    return max(12, int(base * params.density * (limits["max_dots"] / 4000)))


def _max_paths(params: StyleParams) -> int:
    return int(QUALITY_LIMITS[params.quality]["max_paths"])


def _bucket_passes(prefix: str, buckets: dict[str, list[Polyline]]) -> list:
    return [
        make_pass(f"{prefix}-{pid}", f"{prefix} {pid}", pid, polys)
        for pid, polys in buckets.items()
        if polys
    ]


def _pen_cycle(pens, i: int):
    return pens[i % len(pens)]


def _sample_sites_page(params, paper, orientation, image_path, image_array, count: int):
    """Sites in page mm; optionally image-weighted then mapped."""
    rng = rng_from_seed(params.seed)
    pw, ph, box = _page_ctx(paper, orientation)
    x0, y0, x1, y1 = box
    w_mm, h_mm = x1 - x0, y1 - y0
    if image_path or image_array is not None:
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        ih, iw = lum.shape
        sites_img = weighted_sites(lum, count, rng)
        sites = [
            map_to_page(x, y, img_w=iw, img_h=ih, page_w=pw, page_h=ph) for x, y in sites_img
        ]
    else:
        sites = [
            (float(rng.uniform(x0, x1)), float(rng.uniform(y0, y1))) for _ in range(count)
        ]
    return sites, pw, ph, box


class _Voronoi:
    id = "voronoi"
    name = "Voronoi Cells"
    category = "pattern"
    description = "Delaunay dual cell outlines from seeded or image-weighted sites"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        n = _site_count(params, 100)
        sites, pw, ph, box = _sample_sites_page(params, paper, orientation, image_path, image_array, n)
        cells = voronoi_cells(sites, box)
        cells = budget_take(cells, _max_paths(params))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for i, cell in enumerate(cells):
            pen = _pen_cycle(pens, i)
            buckets[pen.id].append(Polyline(points=cell, pen_id=pen.id, closed=True))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("voronoi", buckets),
            seed=params.seed,
            meta={"style": self.id, "sites": len(sites)},
        )


class _Delaunay:
    id = "delaunay"
    name = "Delaunay Mesh"
    category = "pattern"
    description = "Triangulation edges over seeded or image-weighted sites"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        n = _site_count(params, 120)
        sites, pw, ph, box = _sample_sites_page(params, paper, orientation, image_path, image_array, n)
        edges = delaunay_edges(sites)
        edges = budget_take(edges, _max_paths(params))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for i, (a, b) in enumerate(edges):
            clipped = clip_segment(a, b, box)
            if clipped is None:
                continue
            pen = _pen_cycle(pens, i)
            buckets[pen.id].append(Polyline(points=[clipped[0], clipped[1]], pen_id=pen.id))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("delaunay", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _VoronoiStipple:
    id = "voronoi_stipple"
    name = "Voronoi Stipple"
    category = "pattern"
    description = "Tone-weighted sites with short radial marks and light cell edges"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        n = _site_count(params, 200)
        sites, pw, ph, box = _sample_sites_page(params, paper, orientation, image_path, image_array, n)
        cells = voronoi_cells(sites, box)
        cells = budget_take(cells, max(20, _max_paths(params) // 4))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        rng = rng_from_seed(params.seed + 1)
        for i, cell in enumerate(cells):
            pen = _pen_cycle(pens, i)
            if len(cell) >= 2:
                buckets[pen.id].append(Polyline(points=cell, pen_id=pen.id, closed=True))
        mark = max(0.4, 1.2 / params.density)
        for i, (x, y) in enumerate(sites):
            pen = _pen_cycle(pens, i)
            ang = float(rng.uniform(0, math.pi))
            dx, dy = mark * math.cos(ang), mark * math.sin(ang)
            buckets[pen.id].append(Polyline(points=[(x - dx, y - dy), (x + dx, y + dy)], pen_id=pen.id))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("voronoi-stipple", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _Hexbin:
    id = "hexbin"
    name = "Hex Bin"
    category = "pattern"
    description = "Hexagonal lattice with image-colored outlines and hatch fills"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        rgb = _img(params, image_path, image_array)
        ih, iw = rgb.shape[:2]
        r = max(3.0, 8.0 / params.density)
        dx = 1.5 * r
        dy = math.sqrt(3) * r
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        outlines: list[Polyline] = []
        mortar = pens[0]
        row = 0
        y = y0 + r
        path_budget = _max_paths(params)
        count = 0
        while y < y1 - r and count < path_budget:
            x = x0 + r + (0.75 * r if row % 2 else 0)
            while x < x1 - r and count < path_budget:
                # Sample image at mapped hex center
                u = (x - x0) / max(x1 - x0, 1e-6) * (iw - 1)
                v = (y - y0) / max(y1 - y0, 1e-6) * (ih - 1)
                rr, gg, bb = rgb[int(np.clip(v, 0, ih - 1)), int(np.clip(u, 0, iw - 1))]
                pen = nearest_pen(palette, int(rr), int(gg), int(bb))
                hex_pts = circle_points(x, y, r * 0.95, n=6, closed=True)
                # Flatten to regular hex (equal angles already from circle_points n=6)
                outlines.append(Polyline(points=hex_pts, pen_id=mortar.id, closed=True))
                for line in hatch_rect(x - r * 0.6, y - r * 0.5, x + r * 0.6, y + r * 0.5, max(0.8, pen.profile.width_mm)):
                    buckets[pen.id].append(Polyline(points=line, pen_id=pen.id))
                count += 1
                x += dx
            row += 1
            y += dy
        passes = [make_pass("hexbin-outline", "Hex outline", mortar.id, outlines)]
        passes.extend(_bucket_passes("hexbin", buckets))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _ForcePack:
    id = "force_pack"
    name = "Force Pack"
    category = "pattern"
    description = "Collision-packed circles from a short force relaxation"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        n = _site_count(params, 60)
        radii = [float(rng.uniform(1.5, 6.0 / params.density)) for _ in range(n)]
        xs = np.array([rng.uniform(x0, x1) for _ in range(n)], dtype=np.float64)
        ys = np.array([rng.uniform(y0, y1) for _ in range(n)], dtype=np.float64)
        # Simple iterative repulsion
        iters = max(8, int(20 * params.density))
        for _ in range(iters):
            for i in range(n):
                for j in range(i + 1, n):
                    dx = xs[i] - xs[j]
                    dy = ys[i] - ys[j]
                    dist = math.hypot(dx, dy) + 1e-9
                    min_d = radii[i] + radii[j]
                    if dist < min_d:
                        push = (min_d - dist) * 0.5
                        xs[i] += dx / dist * push
                        ys[i] += dy / dist * push
                        xs[j] -= dx / dist * push
                        ys[j] -= dy / dist * push
            xs = np.clip(xs, x0 + 1, x1 - 1)
            ys = np.clip(ys, y0 + 1, y1 - 1)
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for i in range(n):
            pen = _pen_cycle(pens, i)
            pts = circle_points(float(xs[i]), float(ys[i]), radii[i], n=24, closed=True)
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id, closed=True))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("force-pack", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _PoissonDisc:
    id = "poisson_disc"
    name = "Poisson Disc"
    category = "pattern"
    description = "Blue-noise point field rendered as short oriented marks"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        radius = max(1.2, 4.5 / params.density)
        pts = poisson_disc(
            x1 - x0,
            y1 - y0,
            radius,
            rng,
            max_points=int(QUALITY_LIMITS[params.quality]["max_dots"]),
        )
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        mark = radius * 0.45
        for i, (lx, ly) in enumerate(pts):
            x, y = x0 + lx, y0 + ly
            pen = _pen_cycle(pens, i)
            ang = (i * 0.7) % math.pi
            buckets[pen.id].append(
                Polyline(
                    points=[
                        (x - mark * math.cos(ang), y - mark * math.sin(ang)),
                        (x + mark * math.cos(ang), y + mark * math.sin(ang)),
                    ],
                    pen_id=pen.id,
                )
            )
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("poisson", buckets),
            seed=params.seed,
            meta={"style": self.id, "points": len(pts)},
        )


class _CirclePack:
    id = "circle_pack"
    name = "Circle Pack"
    category = "pattern"
    description = "Recursive hierarchical circle packing strokes"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r0 = min(x1 - x0, y1 - y0) / 2 * 0.95
        max_depth = max(2, min(5, int(2 + params.density * 2)))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        count = 0
        budget = _max_paths(params)

        def pack(x, y, r, depth, pen_i):
            nonlocal count
            if count >= budget or r < 1.2:
                return
            pen = _pen_cycle(pens, pen_i)
            buckets[pen.id].append(Polyline(points=circle_points(x, y, r, n=28, closed=True), pen_id=pen.id, closed=True))
            count += 1
            if depth >= max_depth:
                return
            # Place child circles around ring
            n_child = 3 + (depth % 3)
            child_r = r * 0.38
            for k in range(n_child):
                ang = 2 * math.pi * k / n_child + float(rng.uniform(0, 0.2))
                dist = r - child_r * 1.05
                pack(x + dist * math.cos(ang), y + dist * math.sin(ang), child_r, depth + 1, pen_i + k + 1)
            pack(x, y, r * 0.32, depth + 1, pen_i + 7)

        pack(cx, cy, r0, 0, 0)
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("circle-pack", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _MarchingSquares:
    id = "marching_squares"
    name = "Marching Squares"
    category = "pattern"
    description = "True isolines from image luminance via marching squares"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        # Downsample for speed
        step = max(1, int(3 / params.density))
        grid = lum[::step, ::step]
        pw, ph = page_size(paper, orientation)
        ih, iw = lum.shape
        # Map grid cell to page via image coords
        levels = np.linspace(40, 220, min(10, max(3, len(pens) * 2)))
        # Build in image space then map
        result = marching_squares(grid, levels.tolist(), x0=0, y0=0, x_scale=step, y_scale=step)
        passes = []
        for i, (level, chains) in enumerate(result):
            pen = _pen_cycle(pens, i)
            polys = []
            for chain in budget_take(chains, max(10, _max_paths(params) // max(1, len(levels)))):
                pts = [
                    map_to_page(x, y, img_w=iw, img_h=ih, page_w=pw, page_h=ph) for x, y in chain
                ]
                if len(pts) >= 2:
                    polys.append(Polyline(points=pts, pen_id=pen.id))
            if polys:
                passes.append(make_pass(f"ms-{i}", f"Isoline {level:.0f}", pen.id, polys))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _DensityField:
    id = "density_field"
    name = "Density Field"
    category = "pattern"
    description = "KDE-style density isolines from seeded point clouds (no image required)"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        w_mm, h_mm = x1 - x0, y1 - y0
        n = _site_count(params, 80)
        # Cluster a few gaussians
        centers = [(float(rng.uniform(0.2, 0.8) * w_mm), float(rng.uniform(0.2, 0.8) * h_mm)) for _ in range(4)]
        pts = []
        for _ in range(n):
            cx, cy = centers[int(rng.integers(0, len(centers)))]
            pts.append((cx + float(rng.normal(0, w_mm * 0.12)), cy + float(rng.normal(0, h_mm * 0.12))))
        cols = max(24, int(48 * params.density))
        rows = max(24, int(48 * params.density * h_mm / w_mm))
        grid, xs, ys = density_grid(pts, w_mm, h_mm, cols=cols, rows=rows)
        if grid.max() <= 0:
            grid = grid + 1e-6
        levels = np.linspace(grid.max() * 0.15, grid.max() * 0.9, min(8, max(3, len(pens))))
        result = marching_squares(grid, levels.tolist(), x0=x0, y0=y0, x_scale=xs, y_scale=ys)
        passes = []
        for i, (level, chains) in enumerate(result):
            pen = _pen_cycle(pens, i)
            polys = []
            for chain in chains:
                for run in clip_polyline(chain, box):
                    if len(run) >= 2:
                        polys.append(Polyline(points=run, pen_id=pen.id))
            if polys:
                passes.append(make_pass(f"density-{i}", f"Density {i}", pen.id, polys[: _max_paths(params)]))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _RadialBurst:
    id = "radial_burst"
    name = "Radial Burst"
    category = "pattern"
    description = "Concentric arcs and rays in palette bands"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r_max = min(x1 - x0, y1 - y0) / 2 * 0.95
        rings = max(6, int(18 * params.density))
        rays = max(12, int(36 * params.density))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for i in range(rings):
            r = r_max * (i + 1) / rings
            pen = _pen_cycle(pens, i)
            buckets[pen.id].append(Polyline(points=circle_points(cx, cy, r, n=64, closed=True), pen_id=pen.id, closed=True))
        for j in range(rays):
            ang = 2 * math.pi * j / rays
            pen = _pen_cycle(pens, j)
            buckets[pen.id].append(
                Polyline(
                    points=[(cx + 2 * math.cos(ang), cy + 2 * math.sin(ang)), (cx + r_max * math.cos(ang), cy + r_max * math.sin(ang))],
                    pen_id=pen.id,
                )
            )
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("radial-burst", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _StreamRibbons:
    id = "stream_ribbons"
    name = "Stream Ribbons"
    category = "pattern"
    description = "Stacked streamgraph-like ribbons as open strokes"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        n_x = max(20, int(40 * params.density))
        n_layers = max(3, min(len(pens) * 2, int(6 * params.density)))
        xs = np.linspace(x0, x1, n_x)
        # Random walk thicknesses
        layers = []
        for li in range(n_layers):
            base = np.cumsum(rng.normal(0, 1, n_x))
            base = base - base.min()
            base = base / (base.max() + 1e-9) * ((y1 - y0) * 0.08)
            layers.append(base + 2)
        stack = np.zeros(n_x)
        # Center stack
        total = sum(layers)
        y_start = y0 + (y1 - y0 - total.max()) / 2
        passes = []
        for li, thick in enumerate(layers):
            pen = _pen_cycle(pens, li)
            top = y_start + stack + thick
            bottom = y_start + stack
            stack = stack + thick
            # Midline ribbon
            mid = (top + bottom) / 2
            pts = list(zip(xs.tolist(), mid.tolist()))
            # Also outline top
            top_pts = list(zip(xs.tolist(), top.tolist()))
            polys = [
                Polyline(points=pts, pen_id=pen.id),
                Polyline(points=top_pts, pen_id=pen.id),
            ]
            passes.append(make_pass(f"stream-{li}", f"Ribbon {li}", pen.id, polys))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _ChordArcs:
    id = "chord_arcs"
    name = "Chord Arcs"
    category = "pattern"
    description = "Circular chord / metro-arc ornament"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = min(x1 - x0, y1 - y0) / 2 * 0.9
        n = max(8, int(16 * params.density))
        nodes = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        # Outer ring
        buckets[pens[0].id].append(Polyline(points=circle_points(cx, cy, r, n=72, closed=True), pen_id=pens[0].id, closed=True))
        # Random chords as quadratic-ish arcs via mid bulge
        n_chords = max(n, int(n * 1.5 * params.density))
        for k in range(n_chords):
            i = int(rng.integers(0, n))
            j = int(rng.integers(0, n))
            if i == j:
                continue
            a, b = nodes[i], nodes[j]
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            # Bulge toward center
            bulge = 0.35
            mid = (mx + (cx - mx) * bulge, my + (cy - my) * bulge)
            # Sample bezier
            pts = []
            for t in np.linspace(0, 1, 24):
                u = 1 - t
                x = u * u * a[0] + 2 * u * t * mid[0] + t * t * b[0]
                y = u * u * a[1] + 2 * u * t * mid[1] + t * t * b[1]
                pts.append((float(x), float(y)))
            pen = _pen_cycle(pens, k)
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("chord", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _Lissajous:
    id = "lissajous"
    name = "Lissajous"
    category = "pattern"
    description = "Multi-pen parametric Lissajous curves"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ax = (x1 - x0) / 2 * 0.9
        ay = (y1 - y0) / 2 * 0.9
        n_curves = max(2, min(len(pens), int(3 * params.density)))
        samples = max(200, int(600 * params.density))
        passes = []
        for i in range(n_curves):
            pen = _pen_cycle(pens, i)
            a = int(rng.integers(2, 7))
            b = int(rng.integers(2, 7))
            while b == a:
                b = int(rng.integers(2, 7))
            delta = float(rng.uniform(0, math.pi))
            pts = []
            for s in range(samples):
                t = 2 * math.pi * s / (samples - 1)
                x = cx + ax * math.sin(a * t + delta)
                y = cy + ay * math.sin(b * t)
                pts.append((x, y))
            passes.append(make_pass(f"lissajous-{i}", f"Lissajous {a}:{b}", pen.id, [Polyline(points=pts, pen_id=pen.id)]))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _WaveInterfere:
    id = "wave_interfere"
    name = "Wave Interference"
    category = "pattern"
    description = "Two-source interference isolines"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        w_mm, h_mm = x1 - x0, y1 - y0
        s1 = (x0 + w_mm * float(rng.uniform(0.25, 0.4)), y0 + h_mm * float(rng.uniform(0.3, 0.7)))
        s2 = (x0 + w_mm * float(rng.uniform(0.6, 0.75)), y0 + h_mm * float(rng.uniform(0.3, 0.7)))
        cols = max(32, int(56 * params.density))
        rows = max(32, int(56 * params.density * h_mm / w_mm))
        xs = np.linspace(0, w_mm, cols)
        ys = np.linspace(0, h_mm, rows)
        xx, yy = np.meshgrid(xs, ys)
        k = 0.35 * params.density
        d1 = np.hypot(xx - (s1[0] - x0), yy - (s1[1] - y0))
        d2 = np.hypot(xx - (s2[0] - x0), yy - (s2[1] - y0))
        field = np.sin(k * d1) + np.sin(k * d2)
        levels = np.linspace(field.min() * 0.8, field.max() * 0.8, min(9, max(4, len(pens) + 2)))
        result = marching_squares(
            field, levels.tolist(), x0=x0, y0=y0, x_scale=w_mm / max(cols - 1, 1), y_scale=h_mm / max(rows - 1, 1)
        )
        passes = []
        for i, (level, chains) in enumerate(result):
            pen = _pen_cycle(pens, i)
            polys = [Polyline(points=c, pen_id=pen.id) for c in chains if len(c) >= 2]
            polys = polys[: _max_paths(params) // max(1, len(levels))]
            if polys:
                passes.append(make_pass(f"wave-{i}", f"Wave {i}", pen.id, polys))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _GridWarp:
    id = "grid_warp"
    name = "Grid Warp"
    category = "pattern"
    description = "Warped lattice from noise or image gradient"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        cols = max(8, int(16 * params.density))
        rows = max(10, int(20 * params.density))
        xs = np.linspace(x0, x1, cols)
        ys = np.linspace(y0, y1, rows)
        # Displacement field
        amp = min(x1 - x0, y1 - y0) * 0.04 * params.density
        if image_path or image_array is not None:
            rgb = _img(params, image_path, image_array)
            lum = luminance(rgb)
            gy, gx = np.gradient(lum)
            ih, iw = lum.shape

            def disp(x, y):
                u = int(np.clip((x - x0) / max(x1 - x0, 1) * (iw - 1), 0, iw - 1))
                v = int(np.clip((y - y0) / max(y1 - y0, 1) * (ih - 1), 0, ih - 1))
                return gx[v, u] * amp * 0.02, gy[v, u] * amp * 0.02
        else:
            fx = float(rng.uniform(1.5, 3.5))
            fy = float(rng.uniform(1.5, 3.5))
            phase = float(rng.uniform(0, math.pi))

            def disp(x, y):
                nx = (x - x0) / max(x1 - x0, 1)
                ny = (y - y0) / max(y1 - y0, 1)
                return amp * math.sin(fx * math.pi * ny + phase), amp * math.cos(fy * math.pi * nx)

        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        # Horizontal lines
        for ri, y in enumerate(ys):
            pts = []
            for x in xs:
                dx, dy = disp(float(x), float(y))
                pts.append((float(x) + dx, float(y) + dy))
            pen = _pen_cycle(pens, ri)
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        # Vertical lines
        for ci, x in enumerate(xs):
            pts = []
            for y in ys:
                dx, dy = disp(float(x), float(y))
                pts.append((float(x) + dx, float(y) + dy))
            pen = _pen_cycle(pens, ci)
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("grid-warp", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


def _squarify(sizes: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Simple squarified treemap rows; returns list of (x,y,w,h)."""
    if not sizes or w <= 0 or h <= 0:
        return []
    total = sum(sizes) or 1.0
    sizes = [s / total * (w * h) for s in sizes]
    rects: list[tuple[float, float, float, float]] = []
    # Vertical strip packing by area
    i = 0
    cx, cy = x, y
    remain_w, remain_h = w, h
    while i < len(sizes):
        # Fill a row
        row_area = 0.0
        row: list[float] = []
        horizontal = remain_w >= remain_h
        while i < len(sizes):
            row.append(sizes[i])
            row_area += sizes[i]
            i += 1
            # Stop when row would be "square enough" or last
            if horizontal:
                row_h = row_area / remain_w if remain_w else 0
                if len(row) > 1 and row_h > remain_w / len(row):
                    break
            else:
                row_w = row_area / remain_h if remain_h else 0
                if len(row) > 1 and row_w > remain_h / len(row):
                    break
            if i >= len(sizes):
                break
        if horizontal:
            row_h = row_area / remain_w if remain_w else 0
            rx = cx
            for a in row:
                rw = a / row_h if row_h else 0
                rects.append((rx, cy, rw, row_h))
                rx += rw
            cy += row_h
            remain_h -= row_h
        else:
            row_w = row_area / remain_h if remain_h else 0
            ry = cy
            for a in row:
                rh = a / row_w if row_w else 0
                rects.append((cx, ry, row_w, rh))
                ry += rh
            cx += row_w
            remain_w -= row_w
    return rects


class _TreemapStroke:
    id = "treemap_stroke"
    name = "Treemap Stroke"
    category = "pattern"
    description = "Squarified treemap as nested rectangle strokes"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        n = max(8, int(20 * params.density))
        sizes = [float(rng.uniform(0.3, 1.5)) for _ in range(n)]
        rects = _squarify(sizes, x0, y0, x1 - x0, y1 - y0)
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        # Outer frame
        buckets[pens[0].id].append(Polyline(points=rect_outline(x0, y0, x1, y1), pen_id=pens[0].id, closed=True))
        for i, (rx, ry, rw, rh) in enumerate(rects):
            if rw < 0.5 or rh < 0.5:
                continue
            pen = _pen_cycle(pens, i)
            buckets[pen.id].append(
                Polyline(points=rect_outline(rx, ry, rx + rw, ry + rh), pen_id=pen.id, closed=True)
            )
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("treemap", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


_SYMBOLS = {
    "circle": lambda cx, cy, s: circle_points(cx, cy, s, n=20, closed=True),
    "cross": lambda cx, cy, s: None,  # special
    "diamond": lambda cx, cy, s: [
        (cx, cy - s),
        (cx + s, cy),
        (cx, cy + s),
        (cx - s, cy),
        (cx, cy - s),
    ],
    "triangle": lambda cx, cy, s: [
        (cx, cy - s),
        (cx + s * 0.866, cy + s * 0.5),
        (cx - s * 0.866, cy + s * 0.5),
        (cx, cy - s),
    ],
    "square": lambda cx, cy, s: rect_outline(cx - s * 0.7, cy - s * 0.7, cx + s * 0.7, cy + s * 0.7),
}


class _SymbolStamp:
    id = "symbol_stamp"
    name = "Symbol Stamp"
    category = "pattern"
    description = "d3-symbol-like glyphs stamped on a Poisson field"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        radius = max(4.0, 10.0 / params.density)
        pts = poisson_disc(
            x1 - x0,
            y1 - y0,
            radius,
            rng,
            max_points=min(2000, int(QUALITY_LIMITS[params.quality]["max_dots"] // 2)),
        )
        kinds = list(_SYMBOLS.keys())
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        s = radius * 0.28
        for i, (lx, ly) in enumerate(pts):
            x, y = x0 + lx, y0 + ly
            pen = _pen_cycle(pens, i)
            kind = kinds[i % len(kinds)]
            if kind == "cross":
                buckets[pen.id].append(Polyline(points=[(x - s, y), (x + s, y)], pen_id=pen.id))
                buckets[pen.id].append(Polyline(points=[(x, y - s), (x, y + s)], pen_id=pen.id))
            else:
                shape = _SYMBOLS[kind](x, y, s)
                if shape:
                    buckets[pen.id].append(Polyline(points=shape, pen_id=pen.id, closed=True))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=_bucket_passes("symbol", buckets),
            seed=params.seed,
            meta={"style": self.id},
        )


class _RadialArea:
    id = "radial_area"
    name = "Radial Area"
    category = "pattern"
    description = "Polar rose / radial area curves in multi-pen"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pens = ink_pens(palette)
        rng = rng_from_seed(params.seed)
        pw, ph, box = _page_ctx(paper, orientation)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r_max = min(x1 - x0, y1 - y0) / 2 * 0.92
        n_curves = max(2, min(len(pens) + 1, int(4 * params.density)))
        samples = max(180, int(360 * params.density))
        passes = []
        for i in range(n_curves):
            pen = _pen_cycle(pens, i)
            k = int(rng.integers(2, 8))
            phase = float(rng.uniform(0, math.pi))
            scale = r_max * (0.55 + 0.4 * (i + 1) / n_curves)
            pts = []
            for s in range(samples + 1):
                t = 2 * math.pi * s / samples
                # Rose curve r = cos(kθ)
                r = scale * abs(math.cos(k * t + phase))
                pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
            passes.append(make_pass(f"radial-area-{i}", f"Rose k={k}", pen.id, [Polyline(points=pts, pen_id=pen.id)]))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


_ENGINES = [
    _Voronoi(),
    _Delaunay(),
    _VoronoiStipple(),
    _Hexbin(),
    _ForcePack(),
    _PoissonDisc(),
    _CirclePack(),
    _MarchingSquares(),
    _DensityField(),
    _RadialBurst(),
    _StreamRibbons(),
    _ChordArcs(),
    _Lissajous(),
    _WaveInterfere(),
    _GridWarp(),
    _TreemapStroke(),
    _SymbolStamp(),
    _RadialArea(),
]

for _e in _ENGINES:
    register(_e)
