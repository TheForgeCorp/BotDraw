"""Expressive / artistic multicolor style engines."""

from __future__ import annotations

import math
from uuid import uuid4

import numpy as np

from botdraw.core.models import (
    QUALITY_LIMITS,
    LayeredSVG,
    PaperSize,
    PaletteSet,
    Polyline,
    StyleParams,
)
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, nearest_pen
from botdraw.styles import page_size, register
from botdraw.styles.image_utils import luminance, load_image_array, map_to_page, synthetic_portrait


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _img(params: StyleParams, image_path, image_array):
    limits = QUALITY_LIMITS[params.quality]
    if image_array is not None:
        return image_array
    if image_path:
        return load_image_array(image_path, int(limits["image_max"]))
    return synthetic_portrait(int(limits["image_max"]))


class _Stipple:
    id = "stipple"
    name = "Pointillism / Stipple"
    category = "artistic"
    description = "Weighted Voronoi-ish stipple quantized to palette pens"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper)
        limits = QUALITY_LIMITS[params.quality]
        n = int(limits["max_dots"] * params.density)
        rng = _rng(params.seed)
        # Rejection sampling denser in dark areas
        pts = []
        attempts = 0
        while len(pts) < n and attempts < n * 40:
            attempts += 1
            x = rng.integers(0, w)
            y = rng.integers(0, h)
            brightness = lum[y, x] / 255.0
            if rng.random() > brightness:
                pts.append((x, y))
        # Lloyd-ish relaxation
        pts = np.array(pts, dtype=np.float64)
        for _ in range(int(limits["lloyd_iters"])):
            if len(pts) == 0:
                break
            # Simple local pull toward darker neighbors
            new_pts = pts.copy()
            for i, (x, y) in enumerate(pts):
                ix, iy = int(np.clip(x, 0, w - 1)), int(np.clip(y, 0, h - 1))
                gx = (lum[iy, min(ix + 1, w - 1)] - lum[iy, max(ix - 1, 0)]) / 255.0
                gy = (lum[min(iy + 1, h - 1), ix] - lum[max(iy - 1, 0), ix]) / 255.0
                new_pts[i, 0] = np.clip(x - gx * 2, 0, w - 1)
                new_pts[i, 1] = np.clip(y - gy * 2, 0, h - 1)
            pts = new_pts

        pens = ink_pens(palette)
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for x, y in pts:
            ix, iy = int(x), int(y)
            r, g, b = rgb[iy, ix]
            pen = nearest_pen(palette, int(r), int(g), int(b))
            px, py = map_to_page(x, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
            rdot = 0.15 + (1 - lum[iy, ix] / 255.0) * 0.35
            # Tiny circle as polyline
            circle = [
                (px + rdot * math.cos(t), py + rdot * math.sin(t))
                for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)
            ]
            buckets[pen.id].append(Polyline(points=circle + [circle[0]], pen_id=pen.id, closed=True))

        passes = [
            make_pass(f"stipple-{pid}", f"Stipple {pid}", pid, polys)
            for pid, polys in buckets.items()
            if polys
        ]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Flow:
    id = "flow"
    name = "Flow Field"
    category = "artistic"
    description = "Noise-driven particle trails mapped to palette"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper)
        rng = _rng(params.seed)
        pens = ink_pens(palette)
        limits = QUALITY_LIMITS[params.quality]
        n_paths = int(min(limits["max_paths"], 400 * params.density))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for i in range(n_paths):
            x = rng.uniform(0, w - 1)
            y = rng.uniform(0, h - 1)
            pts_img = []
            for _ in range(40):
                ix, iy = int(x), int(y)
                if not (0 <= ix < w and 0 <= iy < h):
                    break
                pts_img.append((x, y))
                angle = (lum[iy, ix] / 255.0) * math.pi * 2 + i * 0.01
                x += math.cos(angle) * 2.5
                y += math.sin(angle) * 2.5
            if len(pts_img) < 2:
                continue
            mx, my = pts_img[len(pts_img) // 2]
            r, g, b = rgb[int(my), int(mx)]
            pen = nearest_pen(palette, int(r), int(g), int(b))
            page_pts = [
                map_to_page(px, py, img_w=w, img_h=h, page_w=pw, page_h=ph) for px, py in pts_img
            ]
            buckets[pen.id].append(Polyline(points=page_pts, pen_id=pen.id))
        passes = [
            make_pass(f"flow-{pid}", f"Flow {pid}", pid, polys)
            for pid, polys in buckets.items()
            if polys
        ]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Hatch:
    id = "hatch"
    name = "Hatching / Lithograph"
    category = "artistic"
    description = "Cross-hatch density from tone with multi-pen layers"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper)
        pens = ink_pens(palette)[:3] or ink_pens(palette)
        step = max(2, int(8 / params.density))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for y in range(0, h, step):
            for x in range(0, w, step):
                tone = lum[y, x] / 255.0
                if tone > 0.85:
                    continue
                pen = pens[0] if tone < 0.35 else pens[min(1, len(pens) - 1)] if tone < 0.6 else pens[min(2, len(pens) - 1)]
                x0, y0 = map_to_page(x, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                x1, y1 = map_to_page(x + step, y + step, img_w=w, img_h=h, page_w=pw, page_h=ph)
                buckets[pen.id].append(Polyline(points=[(x0, y0), (x1, y1)], pen_id=pen.id))
                if tone < 0.4:
                    buckets[pen.id].append(Polyline(points=[(x1, y0), (x0, y1)], pen_id=pen.id))
        passes = [
            make_pass(f"hatch-{pid}", f"Hatch {pid}", pid, polys)
            for pid, polys in buckets.items()
            if polys
        ]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Contour:
    id = "contour"
    name = "Contour / Topographic"
    category = "artistic"
    description = "Luminance band contours in multi-pen"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        bands = np.linspace(40, 220, min(8, max(3, len(pens) * 2)))
        passes = []
        for i, thr in enumerate(bands):
            pen = pens[i % len(pens)]
            polys = []
            # Horizontal scan for threshold crossings approximated as segments
            for y in range(0, h, 3):
                row = lum[y]
                run = None
                for x in range(w):
                    inside = row[x] < thr
                    if inside and run is None:
                        run = x
                    elif not inside and run is not None:
                        if x - run > 2:
                            p0 = map_to_page(run, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                            p1 = map_to_page(x, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                            polys.append(Polyline(points=[p0, p1], pen_id=pen.id))
                        run = None
            if polys:
                passes.append(make_pass(f"contour-{i}", f"Contour {thr:.0f}", pen.id, polys))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Abstract:
    id = "abstract"
    name = "Abstract Geometric"
    category = "artistic"
    description = "Recursive subdivision and circle packing with palette pens"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        pw, ph = page_size(paper)
        rng = _rng(params.seed)
        pens = ink_pens(palette)
        polys_by: dict[str, list[Polyline]] = {p.id: [] for p in pens}

        def subdivide(x, y, w, h, depth):
            if depth <= 0 or min(w, h) < 8:
                pen = pens[int(rng.integers(0, len(pens)))]
                polys_by[pen.id].append(
                    Polyline(points=[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], pen_id=pen.id, closed=True)
                )
                return
            if rng.random() < 0.5:
                cut = w * rng.uniform(0.3, 0.7)
                subdivide(x, y, cut, h, depth - 1)
                subdivide(x + cut, y, w - cut, h, depth - 1)
            else:
                cut = h * rng.uniform(0.3, 0.7)
                subdivide(x, y, w, cut, depth - 1)
                subdivide(x, y + cut, w, h - cut, depth - 1)

        margin = 12
        subdivide(margin, margin, pw - 2 * margin, ph - 2 * margin, depth=6)
        # Circle packing accents
        for _ in range(30):
            cx, cy = rng.uniform(20, pw - 20), rng.uniform(20, ph - 20)
            r = rng.uniform(3, 12)
            pen = pens[int(rng.integers(0, len(pens)))]
            circle = [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 24)]
            polys_by[pen.id].append(Polyline(points=circle + [circle[0]], pen_id=pen.id, closed=True))
        passes = [
            make_pass(f"abs-{pid}", f"Abstract {pid}", pid, polys)
            for pid, polys in polys_by.items()
            if polys
        ]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Squiggle:
    id = "squiggle"
    name = "Squiggle / Single-line"
    category = "artistic"
    description = "Luminance-modulated sine paths"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper)
        pens = ink_pens(palette)
        step_y = max(2, int(6 / params.density))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for y in range(0, h, step_y):
            pts = []
            for x in range(0, w, 2):
                amp = (1 - lum[y, x] / 255.0) * 4.0
                yy = y + math.sin(x * 0.2) * amp
                pts.append(map_to_page(x, yy, img_w=w, img_h=h, page_w=pw, page_h=ph))
            if len(pts) < 2:
                continue
            r, g, b = rgb[y, w // 2]
            pen = nearest_pen(palette, int(r), int(g), int(b))
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        passes = [
            make_pass(f"sq-{pid}", f"Squiggle {pid}", pid, polys)
            for pid, polys in buckets.items()
            if polys
        ]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Mosaic:
    id = "mosaic"
    name = "Mosaic / Stained Glass"
    category = "artistic"
    description = "Facet regions with boundary + fill pens"

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        h, w = rgb.shape[:2]
        pw, ph = page_size(paper)
        rng = _rng(params.seed)
        pens = ink_pens(palette)
        border = pens[0]
        cell = max(8, int(24 / params.density))
        outline: list[Polyline] = []
        fills: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                block = rgb[y : y + cell, x : x + cell]
                if block.size == 0:
                    continue
                mean = block.mean(axis=(0, 1))
                pen = nearest_pen(palette, int(mean[0]), int(mean[1]), int(mean[2]))
                x0, y0 = map_to_page(x, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                x1, y1 = map_to_page(min(x + cell, w), min(y + cell, h), img_w=w, img_h=h, page_w=pw, page_h=ph)
                rect = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
                outline.append(Polyline(points=rect, pen_id=border.id, closed=True))
                # Diagonal fill strokes spaced by pen width
                spacing = max(0.8, pen.profile.width_mm)
                yy = y0
                while yy < y1:
                    fills[pen.id].append(Polyline(points=[(x0, yy), (x1, yy)], pen_id=pen.id))
                    yy += spacing
        passes = [make_pass("mosaic-border", "Mosaic border", border.id, outline)]
        for pid, polys in fills.items():
            if polys:
                passes.append(make_pass(f"mosaic-fill-{pid}", f"Fill {pid}", pid, polys, kind="fill"))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


for _eng in (_Stipple(), _Flow(), _Hatch(), _Contour(), _Abstract(), _Squiggle(), _Mosaic()):
    register(_eng)
