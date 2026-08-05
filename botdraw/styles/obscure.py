"""Post-MVP / R&D obscure motifs — available but marked backlog."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, nearest_pen
from botdraw.styles import page_size, register
from botdraw.styles.image_utils import luminance, load_image_array, map_to_page, synthetic_portrait


def _img(params, image_path, image_array, max_side=480):
    if image_array is not None:
        return image_array
    if image_path:
        return load_image_array(image_path, max_side)
    return synthetic_portrait(max_side)


class _Hilbert:
    id = "hilbert"
    name = "Hilbert Curve"
    category = "backlog"
    description = "Space-filling curve modulated by tone"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        # Simple recursive Hilbert order-4
        order = 5
        n = 2**order
        pts = []

        def hilbert(x0, y0, xi, xj, yi, yj, n):
            if n <= 0:
                pts.append((x0 + (xi + yi) / 2, y0 + (xj + yj) / 2))
            else:
                hilbert(x0, y0, yi / 2, yj / 2, xi / 2, xj / 2, n - 1)
                hilbert(x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2, n - 1)
                hilbert(x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2, n - 1)
                hilbert(x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2, n - 1)

        hilbert(0, 0, n, 0, 0, n, order)
        page_pts = []
        buckets: dict[str, list[tuple[float, float]]] = {}
        current = None
        run = []
        for hx, hy in pts:
            ix = int(np.clip(hx / n * (w - 1), 0, w - 1))
            iy = int(np.clip(hy / n * (h - 1), 0, h - 1))
            r, g, b = rgb[iy, ix]
            pen = nearest_pen(palette, int(r), int(g), int(b))
            pt = map_to_page(ix, iy, img_w=w, img_h=h, page_w=pw, page_h=ph)
            if current is None:
                current = pen.id
            if pen.id != current:
                buckets.setdefault(current, [])
                if len(run) >= 2:
                    buckets[current].append(run)
                current = pen.id
                run = [pt]
            else:
                run.append(pt)
        if current and len(run) >= 2:
            buckets.setdefault(current, []).append(run)
        passes = []
        for pid, runs in buckets.items():
            polys = [Polyline(points=r, pen_id=pid) for r in runs]
            passes.append(make_pass(f"hilbert-{pid}", f"Hilbert {pid}", pid, polys))
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id, "backlog": True})


class _Truchet:
    id = "truchet"
    name = "Truchet Tiles"
    category = "pattern"
    description = "Arc tile field from noise"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        rng = np.random.default_rng(params.seed)
        cell = 12
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for y in np.arange(10, ph - 10, cell):
            for x in np.arange(10, pw - 10, cell):
                pen = pens[int(rng.integers(0, len(pens)))]
                if rng.random() < 0.5:
                    arc = [(x + cell / 2 * (1 + math.cos(t)), y + cell / 2 * (1 + math.sin(t))) for t in np.linspace(math.pi, 1.5 * math.pi, 8)]
                else:
                    arc = [(x + cell / 2 * (1 + math.cos(t)), y + cell / 2 * (1 + math.sin(t))) for t in np.linspace(0, 0.5 * math.pi, 8)]
                buckets[pen.id].append(Polyline(points=arc, pen_id=pen.id))
        passes = [make_pass(f"truchet-{pid}", f"Truchet {pid}", pid, polys) for pid, polys in buckets.items() if polys]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id, "backlog": True})


class _Mandala:
    id = "mandala"
    name = "Radial Mandala"
    category = "pattern"
    description = "Radial burst sectors"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        cx, cy = pw / 2, ph / 2
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for ring in range(3, 12):
            r = ring * 8
            pen = pens[ring % len(pens)]
            for k in range(ring * 4):
                a0 = k * 2 * math.pi / (ring * 4)
                a1 = (k + 0.6) * 2 * math.pi / (ring * 4)
                buckets[pen.id].append(
                    Polyline(
                        points=[
                            (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                            (cx + r * math.cos(a1), cy + r * math.sin(a1)),
                        ],
                        pen_id=pen.id,
                    )
                )
        passes = [make_pass(f"man-{pid}", f"Mandala {pid}", pid, polys) for pid, polys in buckets.items() if polys]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id, "backlog": True})


class _StringArt:
    id = "stringart"
    name = "String Art"
    category = "pattern"
    description = "Chord envelope around a circle"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        cx, cy, r = pw / 2, ph / 2, min(pw, ph) * 0.35
        n = 72
        nails = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        polys = []
        step = 11
        for i in range(n):
            j = (i + step) % n
            pen = pens[i % len(pens)]
            polys.append((pen.id, Polyline(points=[nails[i], nails[j]], pen_id=pen.id)))
        buckets: dict[str, list[Polyline]] = {}
        for pid, poly in polys:
            buckets.setdefault(pid, []).append(poly)
        passes = [make_pass(f"str-{pid}", f"String {pid}", pid, ps) for pid, ps in buckets.items()]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id, "backlog": True})


class _Seismograph:
    id = "seismograph"
    name = "Seismograph Rows"
    category = "pattern"
    description = "Stacked waveforms from row scans"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        rgb = _img(params, image_path, image_array)
        lum = luminance(rgb)
        h, w = lum.shape
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
        for yi, y in enumerate(range(0, h, 4)):
            pts = []
            for x in range(0, w, 2):
                amp = (1 - lum[y, x] / 255.0) * 3
                pts.append(map_to_page(x, y + amp, img_w=w, img_h=h, page_w=pw, page_h=ph))
            pen = pens[yi % len(pens)]
            buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))
        passes = [make_pass(f"seis-{pid}", f"Seismo {pid}", pid, polys) for pid, polys in buckets.items() if polys]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id, "backlog": True})


for _e in (_Hilbert(), _Truchet(), _Mandala(), _StringArt(), _Seismograph()):
    register(_e)
