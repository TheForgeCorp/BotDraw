"""Technical / engineering / blueprint styles."""

from __future__ import annotations

import math

import numpy as np

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, Polyline, StyleParams
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens
from botdraw.styles import page_size, register


class _Blueprint:
    id = "blueprint"
    name = "Blueprint Sheet"
    category = "technical"
    description = "Title block, grid, multi-weight technical lines"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        grid_pen = pens[0]
        bold = pens[min(1, len(pens) - 1)]
        accent = pens[min(2, len(pens) - 1)]
        margin = 12
        grid = []
        for x in np.arange(margin, pw - margin + 0.1, 10):
            grid.append(Polyline(points=[(x, margin), (x, ph - margin)], pen_id=grid_pen.id))
        for y in np.arange(margin, ph - margin + 0.1, 10):
            grid.append(Polyline(points=[(margin, y), (pw - margin, y)], pen_id=grid_pen.id))
        frame = [
            Polyline(
                points=[
                    (margin, margin),
                    (pw - margin, margin),
                    (pw - margin, ph - margin),
                    (margin, ph - margin),
                    (margin, margin),
                ],
                pen_id=bold.id,
                closed=True,
            )
        ]
        # Title block
        tb_x, tb_y = pw - margin - 70, ph - margin - 35
        title = [
            Polyline(
                points=[(tb_x, tb_y), (pw - margin, tb_y), (pw - margin, ph - margin), (tb_x, ph - margin), (tb_x, tb_y)],
                pen_id=bold.id,
                closed=True,
            ),
            Polyline(points=[(tb_x, tb_y + 12), (pw - margin, tb_y + 12)], pen_id=accent.id),
        ]
        # Sample orthographic box
        cx, cy = pw / 2, ph / 2 - 20
        box = [
            Polyline(points=[(cx - 30, cy - 20), (cx + 30, cy - 20), (cx + 30, cy + 20), (cx - 30, cy + 20), (cx - 30, cy - 20)], pen_id=bold.id, closed=True),
            Polyline(points=[(cx - 30, cy - 20), (cx - 15, cy - 35), (cx + 45, cy - 35), (cx + 30, cy - 20)], pen_id=accent.id),
            Polyline(points=[(cx + 30, cy - 20), (cx + 45, cy - 35), (cx + 45, cy + 5), (cx + 30, cy + 20)], pen_id=accent.id),
        ]
        # Dimension line
        dims = [
            Polyline(points=[(cx - 30, cy + 30), (cx + 30, cy + 30)], pen_id=accent.id),
            Polyline(points=[(cx - 30, cy + 27), (cx - 30, cy + 33)], pen_id=accent.id),
            Polyline(points=[(cx + 30, cy + 27), (cx + 30, cy + 33)], pen_id=accent.id),
        ]
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[
                make_pass("bp-grid", "Grid", grid_pen.id, grid),
                make_pass("bp-frame", "Frame", bold.id, frame + title),
                make_pass("bp-geom", "Geometry", bold.id, box),
                make_pass("bp-dims", "Dimensions", accent.id, dims),
            ],
            seed=params.seed,
            meta={"style": self.id},
        )


class _Isometric:
    id = "isometric"
    name = "Isometric Schematic"
    category = "technical"
    description = "Parametric isometric boxes and connectors"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        rng = np.random.default_rng(params.seed)
        polys: list[Polyline] = []

        def iso(x, y, z):
            return pw / 2 + (x - z) * math.cos(math.pi / 6) * 8, ph / 2 + (x + z) * math.sin(math.pi / 6) * 8 - y * 8

        for i in range(5):
            x, y, z = rng.uniform(-6, 6), rng.uniform(0, 4), rng.uniform(-6, 6)
            w, h, d = rng.uniform(1.5, 3), rng.uniform(1, 3), rng.uniform(1.5, 3)
            corners = [
                iso(x, y, z),
                iso(x + w, y, z),
                iso(x + w, y, z + d),
                iso(x, y, z + d),
                iso(x, y + h, z),
                iso(x + w, y + h, z),
                iso(x + w, y + h, z + d),
                iso(x, y + h, z + d),
            ]
            edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
            pen = pens[i % len(pens)]
            for a, b in edges:
                polys.append(Polyline(points=[corners[a], corners[b]], pen_id=pen.id))
        # Group by pen
        buckets: dict[str, list[Polyline]] = {}
        for poly in polys:
            buckets.setdefault(poly.pen_id, []).append(poly)
        passes = [make_pass(f"iso-{pid}", f"Iso {pid}", pid, ps) for pid, ps in buckets.items()]
        return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=params.seed, meta={"style": self.id})


class _PCB:
    id = "pcb"
    name = "PCB Aesthetic"
    category = "technical"
    description = "Traces and pad rings"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        pw, ph = page_size(paper, orientation)
        pens = ink_pens(palette)
        rng = np.random.default_rng(params.seed)
        trace_pen = pens[0]
        pad_pen = pens[min(1, len(pens) - 1)]
        traces = []
        pads = []
        nodes = [(rng.uniform(20, pw - 20), rng.uniform(20, ph - 20)) for _ in range(18)]
        for i in range(len(nodes) - 1):
            a, b = nodes[i], nodes[(i * 3) % len(nodes)]
            mid = (a[0], b[1])
            traces.append(Polyline(points=[a, mid, b], pen_id=trace_pen.id))
        for x, y in nodes:
            r = 2.2
            circle = [(x + r * math.cos(t), y + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 16)]
            pads.append(Polyline(points=circle + [circle[0]], pen_id=pad_pen.id, closed=True))
        return LayeredSVG(
            width_mm=pw,
            height_mm=ph,
            passes=[
                make_pass("pcb-traces", "Traces", trace_pen.id, traces),
                make_pass("pcb-pads", "Pads", pad_pen.id, pads),
            ],
            seed=params.seed,
            meta={"style": self.id},
        )


for _e in (_Blueprint(), _Isometric(), _PCB()):
    register(_e)
