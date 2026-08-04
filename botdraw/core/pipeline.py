"""End-to-end render → optimize → motion plan pipeline."""

from __future__ import annotations

import json

from botdraw.core.jobs import artifact_dir, save_job
from botdraw.core.models import (
    PAPER_MM,
    JobRecord,
    JobStatus,
    LayeredSVG,
    PaperSize,
    PaletteSet,
    QualityPreset,
    StyleParams,
)
from botdraw.core.motion_plan import DEFAULT_PEN_DOWN_MM_S, DEFAULT_PEN_UP_MM_S, compile_motion_plan
from botdraw.core.optimize import optimize_layered
from botdraw.core.svg import save_svg
from botdraw.palettes import load_palette
from botdraw.plotter.emulator import plan_to_emulator_payload
from botdraw.styles import ensure_styles_loaded, get_style


def layers_summary(layered: LayeredSVG, palette: PaletteSet) -> dict:
    passes = []
    for p in layered.passes:
        pen = palette.pen_by_id(p.pen_id)
        opacity = p.opacity_override if p.opacity_override is not None else pen.profile.opacity
        passes.append(
            {
                "id": p.id,
                "name": p.name,
                "kind": p.kind,
                "pen_id": p.pen_id,
                "pen_name": pen.name,
                "board_id": pen.resolved_board_id(),
                "color_hex": pen.color_hex,
                "width_mm": pen.profile.width_mm,
                "opacity": opacity,
                "nib_type": pen.profile.nib_type.value,
                "polyline_count": len(p.polylines),
                "point_count": sum(len(pl.points) for pl in p.polylines),
            }
        )
    return {
        "width_mm": layered.width_mm,
        "height_mm": layered.height_mm,
        "seed": layered.seed,
        "meta": layered.meta,
        "pass_count": len(passes),
        "passes": passes,
    }


def render_job(
    *,
    app: str,
    style_id: str,
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED,
    seed: int = 42,
    density: float = 1.0,
    image_path: str | None = None,
    params_extra: dict | None = None,
    pen_up_speed_mm_s: float = DEFAULT_PEN_UP_MM_S,
    pen_down_speed_mm_s: float = DEFAULT_PEN_DOWN_MM_S,
) -> tuple[JobRecord, dict, dict]:
    ensure_styles_loaded()
    paper_enum = paper if isinstance(paper, PaperSize) else PaperSize(paper)
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
    settings = {
        "app": app,
        "style_id": style_id,
        "palette_id": palette_id,
        "paper": paper_enum.value,
        "quality": quality_enum.value,
        "seed": seed,
        "density": density,
        "pen_up_speed_mm_s": pen_up_speed_mm_s,
        "pen_down_speed_mm_s": pen_down_speed_mm_s,
        "image_path": image_path,
        "params_extra": params_extra or {},
        "paper_mm": list(PAPER_MM[paper_enum]),
    }
    job = JobRecord(
        app=app,
        style_id=style_id,
        seed=seed,
        quality=quality_enum,
        palette_id=palette_id,
        paper=paper_enum,
        params={
            "density": density,
            "pen_up_speed_mm_s": pen_up_speed_mm_s,
            "pen_down_speed_mm_s": pen_down_speed_mm_s,
            **(params_extra or {}),
        },
        status=JobStatus.RENDERING,
    )
    save_job(job)
    try:
        palette = load_palette(palette_id)
        engine = get_style(style_id)
        layered = engine.render(
            palette=palette,
            params=StyleParams(
                seed=seed,
                quality=quality_enum,
                density=density,
                extra=params_extra or {},
            ),
            paper=paper_enum,
            image_path=image_path,
        )
        layered = optimize_layered(layered)
        plan = compile_motion_plan(
            layered,
            palette,
            pen_up_speed_mm_s=pen_up_speed_mm_s,
            pen_down_speed_mm_s=pen_down_speed_mm_s,
        )
        out = artifact_dir(job.id)
        svg_path = save_svg(layered, palette, out / "art.svg")
        motion_path = out / "motion_plan.json"
        plan.save(motion_path)
        layers = layers_summary(layered, palette)
        (out / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
        (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        (out / "palette.json").write_text(palette.model_dump_json(indent=2), encoding="utf-8")
        payload = plan_to_emulator_payload(plan)
        payload["layers"] = layers
        payload["settings"] = settings
        payload_path = out / "emulator.json"
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
        job.status = JobStatus.READY
        job.svg_path = str(svg_path)
        job.motion_path = str(motion_path)
        job.preview_path = str(payload_path)
        save_job(job)
        export_pack = {
            "settings": settings,
            "job": job.model_dump(),
            "layers": layers,
            "palette": json.loads(palette.model_dump_json()),
            "motion_plan": plan.to_dict(),
            "stats": plan.stats.model_dump(),
        }
        (out / "export_pack.json").write_text(json.dumps(export_pack, indent=2), encoding="utf-8")
        return job, payload, layers
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        save_job(job)
        raise
