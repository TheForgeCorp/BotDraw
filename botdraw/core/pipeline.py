"""End-to-end render → optimize → motion plan pipeline."""

from __future__ import annotations

import json

from botdraw.core.jobs import artifact_dir, load_job, save_job
from botdraw.core.models import (
    JobRecord,
    JobStatus,
    LayeredSVG,
    Orientation,
    PaperSize,
    PaletteSet,
    QualityPreset,
    StyleParams,
    paper_dims,
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


def render_from_layered(
    *,
    app: str,
    style_id: str,
    layered: LayeredSVG,
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    orientation: Orientation = Orientation.PORTRAIT,
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED,
    seed: int = 42,
    density: float = 1.0,
    image_path: str | None = None,
    params_extra: dict | None = None,
    pen_up_speed_mm_s: float = DEFAULT_PEN_UP_MM_S,
    pen_down_speed_mm_s: float = DEFAULT_PEN_DOWN_MM_S,
    job_id: str | None = None,
) -> tuple[JobRecord, dict, dict]:
    """Optimize a pre-built LayeredSVG and write job artifacts (same shape as render_job)."""
    paper_enum = paper if isinstance(paper, PaperSize) else PaperSize(paper)
    orientation_enum = orientation if isinstance(orientation, Orientation) else Orientation(orientation)
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
    settings = {
        "app": app,
        "style_id": style_id,
        "palette_id": palette_id,
        "paper": paper_enum.value,
        "orientation": orientation_enum.value,
        "quality": quality_enum.value,
        "seed": seed,
        "density": density,
        "pen_up_speed_mm_s": pen_up_speed_mm_s,
        "pen_down_speed_mm_s": pen_down_speed_mm_s,
        "image_path": image_path,
        "params_extra": params_extra or {},
        "paper_mm": list(paper_dims(paper_enum, orientation_enum)),
    }
    if job_id:
        try:
            job = load_job(job_id)
            job.app = app
            job.style_id = style_id
            job.seed = seed
            job.quality = quality_enum
            job.palette_id = palette_id
            job.paper = paper_enum
            job.orientation = orientation_enum
            job.params = {
                "density": density,
                "pen_up_speed_mm_s": pen_up_speed_mm_s,
                "pen_down_speed_mm_s": pen_down_speed_mm_s,
                **(params_extra or {}),
            }
            job.status = JobStatus.RENDERING
            job.error = None
        except Exception:
            job = JobRecord(
                id=job_id,
                app=app,
                style_id=style_id,
                seed=seed,
                quality=quality_enum,
                palette_id=palette_id,
                paper=paper_enum,
                orientation=orientation_enum,
                params={
                    "density": density,
                    "pen_up_speed_mm_s": pen_up_speed_mm_s,
                    "pen_down_speed_mm_s": pen_down_speed_mm_s,
                    **(params_extra or {}),
                },
                status=JobStatus.RENDERING,
            )
    else:
        job = JobRecord(
            app=app,
            style_id=style_id,
            seed=seed,
            quality=quality_enum,
            palette_id=palette_id,
            paper=paper_enum,
            orientation=orientation_enum,
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
        (out / "layered.json").write_text(layered.model_dump_json(indent=2), encoding="utf-8")
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


def render_job(
    *,
    app: str,
    style_id: str,
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    orientation: Orientation = Orientation.PORTRAIT,
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
    orientation_enum = orientation if isinstance(orientation, Orientation) else Orientation(orientation)
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
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
        orientation=orientation_enum,
        image_path=image_path,
    )
    return render_from_layered(
        app=app,
        style_id=style_id,
        layered=layered,
        palette_id=palette_id,
        paper=paper_enum,
        orientation=orientation_enum,
        quality=quality_enum,
        seed=seed,
        density=density,
        image_path=image_path,
        params_extra=params_extra,
        pen_up_speed_mm_s=pen_up_speed_mm_s,
        pen_down_speed_mm_s=pen_down_speed_mm_s,
    )
