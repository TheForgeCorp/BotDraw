"""Pattern / structure packs: brick, weave, spiral."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import QUALITY_LIMITS, LayeredSVG, Orientation, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, nearest_pen
from botdraw.styles import page_size, register
from botdraw.styles.image_utils import luminance, load_image_array, map_to_page, synthetic_portrait


def _img(params, image_path, image_array):
    limits = QUALITY_LIMITS[params.quality]
    if image_array is not None:
        return image_array
    if image_path:
        mode = (params.extra or {}).get("image_mode") or (params.extra or {}).get("image_type")
        return load_image_array(image_path, int(limits["image_max"]), mode=mode)
    return synthetic_portrait(int(limits["image_max"]))


class _Brick:
    id = "brick"
    name = "Brick Layout"
    category = "pattern"
    description = "Image quantized into multicolor brick courses"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        h, w = rgb.shape[:2]
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        bw, bh = max(6, int(14 / params.density)), max(4, int(8 / params.density))
        mortar = pens[0]
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        outlines: list[Polyline] = []
        row = 0
        for y in range(0, h, bh):
            offset = (bw // 2) if row % 2 else 0
            for x in range(-offset, w, bw):
                x0 = max(0, x)
                x1 = min(w, x + bw)
                y1 = min(h, y + bh)
                if x1 - x0 < 2 or y1 - y < 2:
                    continue
                mean = rgb[y:y1, x0:x1].mean(axis=(0, 1))
                pen = nearest_pen(palette, int(mean[0]), int(mean[1]), int(mean[2]))
                p0 = map_to_page(x0, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                p1 = map_to_page(x1, y1, img_w=w, img_h=h, page_w=pw, page_h=ph)
                rect = [(p0[0], p0[1]), (p1[0], p0[1]), (p1[0], p1[1]), (p0[0], p1[1]), (p0[0], p0[1])]
                outlines.append(Polyline(points=rect, pen_id=mortar.id, closed=True))
                # Fill hatch
                yy = p0[1]
                while yy < p1[1]:
                    buckets[pen.id].append(Polyline(points=[(p0[0], yy), (p1[0], yy)], pen_id=pen.id))
                    yy += max(0.7, pen.profile.width_mm)
            row += 1
        passes = [make_pass("brick-mortar", "Mortar", mortar.id, outlines)]
        for pid, polys in buckets.items():
            if polys:
                passes.append(make_pass(f"brick-{pid}", f"Brick {pid}", pid, polys, kind="fill"))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Weave:
    id = "weave"
    name = "Tapestry / Weave"
    category = "pattern"
    description = "Warp and weft threads colored from image"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        h, w = rgb.shape[:2]
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        step = max(2, int(5 / params.density))
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        # Warp (vertical)
        for x in range(0, w, step):
            pts = [map_to_page(x, y, img_w=w, img_h=h, page_w=pw, page_h=ph) for y in range(0, h, 2)]
            r, g, b = rgb[h // 2, x]
            pen = nearest_pen(palette, int(r), int(g), int(b))
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        # Weft (horizontal) with over/under skip
        for y in range(0, h, step):
            for x0 in range(0, w, step * 2):
                x1 = min(w - 1, x0 + step)
                p0 = map_to_page(x0, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                p1 = map_to_page(x1, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
                r, g, b = rgb[y, (x0 + x1) // 2]
                pen = nearest_pen(palette, int(r), int(g), int(b))
                buckets[pen.id].append(Polyline(points=[p0, p1], pen_id=pen.id))
        passes = [
            make_pass(f"weave-{pid}", f"Weave {pid}", pid, polys)
            for pid, polys in buckets.items()
            if polys
        ]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _Spiral:
    id = "spiral"
    name = "Spiral Forms"
    category = "pattern"
    description = "Archimedean spiral sampling image colors"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = rgb.shape[:2]
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        limits = QUALITY_LIMITS[params.quality]
        turns = int(limits["spiral_turns"] * params.density)
        cx, cy = w / 2, h / 2
        max_r = min(cx, cy) * 0.95
        buckets: dict[str, list[list[tuple[float, float]]]] = {p.id: [] for p in pens}
        current_pen = None
        current_pts: list[tuple[float, float]] = []
        for i in range(turns * 40):
            t = i / 40
            angle = t * 2 * math.pi
            r = max_r * (t / turns)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if not (0 <= x < w and 0 <= y < h):
                continue
            amp = (1 - lum[int(y), int(x)] / 255.0) * 2.5
            x += math.cos(angle) * amp
            y += math.sin(angle) * amp
            rr, gg, bb = rgb[int(np.clip(y, 0, h - 1)), int(np.clip(x, 0, w - 1))]
            pen = nearest_pen(palette, int(rr), int(gg), int(bb))
            pt = map_to_page(x, y, img_w=w, img_h=h, page_w=pw, page_h=ph)
            if current_pen is None:
                current_pen = pen.id
            if pen.id != current_pen:
                if len(current_pts) >= 2:
                    buckets[current_pen].append(current_pts)
                current_pen = pen.id
                current_pts = [pt]
            else:
                current_pts.append(pt)
        if current_pen and len(current_pts) >= 2:
            buckets[current_pen].append(current_pts)
        passes = []
        for pid, runs in buckets.items():
            polys = [Polyline(points=run, pen_id=pid) for run in runs]
            if polys:
                passes.append(make_pass(f"spiral-{pid}", f"Spiral {pid}", pid, polys))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


for _e in (_Brick(), _Weave(), _Spiral()):
    register(_e)
