"""Portrait-tuned style presets over shared engines."""

from __future__ import annotations

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, StyleParams
from botdraw.styles import get_style, register
from botdraw.styles import artistic as artistic_mod  # ensure loaded
from botdraw.styles import patterns as patterns_mod  # noqa: F401


class _PortraitProxy:
    def __init__(self, style_id: str, name: str, description: str, base_id: str, tweaks: dict | None = None):
        self.id = style_id
        self.name = name
        self.category = "portrait"
        self.description = description
        self.base_id = base_id
        self.tweaks = tweaks or {}

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        base = get_style(self.base_id)
        extra = {**params.extra, **self.tweaks, "portrait_profile": True}
        tuned = StyleParams(
            seed=params.seed,
            quality=params.quality,
            density=params.density * float(self.tweaks.get("density_mul", 1.0)),
            scale=params.scale,
            pen_count=params.pen_count,
            extra=extra,
        )
        layered = base.render(
            palette=palette,
            params=tuned,
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        layered.meta["portrait_style"] = self.id
        layered.meta["base_style"] = self.base_id
        return layered


class _Cubism:
    id = "portrait_cubism"
    name = "Cubism Portrait"
    category = "portrait"
    description = "Angular faceted planes over a face crop"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        # Use mosaic with coarser cells + abstract accents via mosaic engine
        base = get_style("mosaic")
        tuned = StyleParams(
            seed=params.seed,
            quality=params.quality,
            density=max(0.4, params.density * 0.55),
            scale=params.scale,
            extra={"cubism": True},
        )
        layered = base.render(
            palette=palette,
            params=tuned,
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        layered.meta["portrait_style"] = self.id
        return layered


class _Dots:
    id = "portrait_dots"
    name = "Dot Halftone Portrait"
    category = "portrait"
    description = "Lighter grid-dot halftone than full pointillism"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        base = get_style("stipple")
        tuned = StyleParams(
            seed=params.seed,
            quality=params.quality,
            density=params.density * 0.55,
            scale=params.scale,
        )
        layered = base.render(
            palette=palette,
            params=tuned,
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        layered.meta["portrait_style"] = self.id
        return layered


class _ColorShade:
    id = "portrait_color_shade"
    name = "Color Shade Portrait"
    category = "portrait"
    description = "Palette-band stroke fills for facial shading"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        base = get_style("hatch")
        tuned = StyleParams(
            seed=params.seed,
            quality=params.quality,
            density=params.density * 1.2,
            scale=params.scale,
        )
        layered = base.render(
            palette=palette,
            params=tuned,
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        layered.meta["portrait_style"] = self.id
        return layered


class _PenSketch:
    id = "portrait_pen"
    name = "Pen Sketch Portrait"
    category = "portrait"
    description = "Loose contour and short pen strokes"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        contour = get_style("contour").render(
            palette=palette,
            params=StyleParams(seed=params.seed, quality=params.quality, density=0.8),
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        hatch = get_style("hatch").render(
            palette=palette,
            params=StyleParams(seed=params.seed + 1, quality=params.quality, density=0.6),
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        contour.passes.extend(hatch.passes)
        contour.meta["portrait_style"] = self.id
        return contour


class _Linework:
    id = "portrait_linework"
    name = "Simple Linework Portrait"
    category = "portrait"
    description = "Clean edge/contour strokes"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        layered = get_style("contour").render(
            palette=palette,
            params=StyleParams(seed=params.seed, quality=params.quality, density=0.7),
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        layered.meta["portrait_style"] = self.id
        return layered


class _TSP:
    id = "portrait_tsp"
    name = "TSP Single-line Portrait"
    category = "portrait"
    description = "Stipple then greedy TSP path (slow — HQ/queue)"

    def render(self, *, palette, params, paper=PaperSize.A4, orientation=Orientation.PORTRAIT, image_path=None, image_array=None):
        from botdraw.core.models import Polyline
        from botdraw.core.svg import make_pass
        from botdraw.palettes import ink_pens

        stippled = get_style("stipple").render(
            palette=palette,
            params=StyleParams(seed=params.seed, quality=params.quality, density=0.7),
            paper=paper,
            orientation=orientation,
            image_path=image_path,
            image_array=image_array,
        )
        # Collect circle centers and greedy tour
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
        pen = ink_pens(palette)[0]
        layered = LayeredSVG(
            width_mm=stippled.width_mm,
            height_mm=stippled.height_mm,
            passes=[make_pass("tsp", "TSP path", pen.id, [Polyline(points=tour, pen_id=pen.id)])],
            seed=params.seed,
            meta={"portrait_style": self.id},
        )
        return layered


PORTRAIT_STYLES = [
    _Linework(),
    _PortraitProxy("portrait_squiggle", "Squiggle Portrait", "SquiggleCam-style face lines", "squiggle"),
    _PenSketch(),
    _ColorShade(),
    _PortraitProxy("portrait_pointillism", "Pointillism Portrait", "Color-quantized stipple portrait", "stipple"),
    _Dots(),
    _Cubism(),
    _PortraitProxy("portrait_hatch", "Hatch Portrait", "Classic multi-pen hatch shading", "hatch"),
    _TSP(),
]

for _e in PORTRAIT_STYLES:
    register(_e)
