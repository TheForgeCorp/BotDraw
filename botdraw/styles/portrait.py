"""Portrait-tuned styles — restyle from PortraitVector when available."""

from __future__ import annotations

from botdraw.core.models import LayeredSVG, PaperSize, StyleParams
from botdraw.portrait.restyle import render_from_vector
from botdraw.styles import register


class _PortraitRestyler:
    def __init__(self, style_id: str, name: str, description: str):
        self.id = style_id
        self.name = name
        self.category = "portrait"
        self.description = description

    def render(self, *, palette, params, paper=PaperSize.A4, image_path=None, image_array=None):
        pv = (params.extra or {}).get("portrait_vector")
        if pv is None:
            # Fallback: ingest on the fly for GenArt-like calls without pipeline wiring
            from botdraw.portrait.ingest import ingest_portrait
            from botdraw.portrait.pens import assign_pens

            mode = (params.extra or {}).get("image_mode") or "photo"
            pv = ingest_portrait(
                image_path,
                image_array=image_array,
                mode=mode,
                quality=params.quality,
                paper=paper,
                auto_frame=True,
            )
            pv = assign_pens(pv, palette, pen_map=(params.extra or {}).get("pen_map"))
        spacing = (params.extra or {}).get("line_spacing_mm")
        layered = render_from_vector(
            self.id,
            pv,
            palette,
            params,
            line_spacing_mm=float(spacing) if spacing is not None else None,
        )
        layered.meta["portrait_style"] = self.id
        return layered


PORTRAIT_STYLES = [
    _PortraitRestyler("portrait_linework", "Simple Linework Portrait", "Edge + region outline from ingest"),
    _PortraitRestyler("portrait_squiggle", "Squiggle Portrait", "Ink-target modulated squiggles"),
    _PortraitRestyler("portrait_pen", "Pen Sketch Portrait", "Edges plus adaptive hatch shade"),
    _PortraitRestyler("portrait_color_shade", "Color Shade Portrait", "Adaptive multi-pen hatch from tone"),
    _PortraitRestyler("portrait_pointillism", "Pointillism Portrait", "Ink-weighted stipple"),
    _PortraitRestyler("portrait_dots", "Dot Halftone Portrait", "Lighter stipple halftone"),
    _PortraitRestyler("portrait_cubism", "Cubism Portrait", "Facet fills from traced regions"),
    _PortraitRestyler("portrait_hatch", "Hatch Portrait", "Classic adaptive hatch shading"),
    _PortraitRestyler("portrait_tsp", "TSP Single-line Portrait", "Stipple centers → greedy tour"),
]

for _e in PORTRAIT_STYLES:
    register(_e)
