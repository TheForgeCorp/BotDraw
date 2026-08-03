"""R&D Lab helpers."""

from __future__ import annotations

from botdraw.core.models import StyleParams, PaperSize
from botdraw.core.optimize import optimize_layered
from botdraw.core.motion_plan import compile_motion_plan
from botdraw.palettes import load_palette
from botdraw.plotter.turntable import annotate_plan_with_rotation, spiral_on_turntable
from botdraw.styles import ensure_styles_loaded, get_style


def render_experimental(style_id: str, *, palette_id: str = "default-6", seed: int = 42, rpm: float = 3.0):
    ensure_styles_loaded()
    palette = load_palette(palette_id)
    engine = get_style(style_id)
    layered = engine.render(palette=palette, params=StyleParams(seed=seed), paper=PaperSize.A4)
    layered = optimize_layered(layered)
    plan = spiral_on_turntable(layered, palette, rpm=rpm)
    return layered, plan
