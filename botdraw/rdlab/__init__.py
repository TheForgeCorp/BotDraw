"""R&D Lab helpers."""

from __future__ import annotations

from botdraw.core.models import Orientation, PaperSize, QualityPreset, StyleParams
from botdraw.core.motion_plan import compile_motion_plan
from botdraw.core.optimize import optimize_layered
from botdraw.palettes import load_palette
from botdraw.plotter.turntable import annotate_plan_with_rotation
from botdraw.styles import ensure_styles_loaded, get_style


def render_experimental(
    style_id: str,
    *,
    palette_id: str = "default-6",
    seed: int = 42,
    rpm: float = 3.0,
    image_path: str | None = None,
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED,
    density: float = 1.0,
    orientation: Orientation = Orientation.PORTRAIT,
):
    ensure_styles_loaded()
    palette = load_palette(palette_id)
    engine = get_style(style_id)
    layered = engine.render(
        palette=palette,
        params=StyleParams(seed=seed, quality=quality, density=density),
        paper=PaperSize.A4,
        orientation=orientation,
        image_path=image_path,
    )
    layered = optimize_layered(layered)
    plan = compile_motion_plan(layered, palette, include_base_theta=True)
    plan = annotate_plan_with_rotation(plan, rpm=rpm)
    return layered, plan
