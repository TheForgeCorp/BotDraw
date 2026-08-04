"""End-to-end render → optimize → motion plan pipeline."""

from __future__ import annotations

import json
from typing import Any

from botdraw.core.jobs import artifact_dir, save_job
from botdraw.core.models import (
    PAPER_MM,
    QUALITY_LIMITS,
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
from botdraw.paper import DEFAULT_PAPER_ID, resolve_paper_color
from botdraw.plotter.emulator import plan_to_emulator_payload
from botdraw.styles import ensure_styles_loaded, get_style


def layers_summary(layered: LayeredSVG, palette: PaletteSet) -> dict:
    passes = []
    path_count = 0
    for p in layered.passes:
        pen = palette.pen_by_id(p.pen_id)
        opacity = p.opacity_override if p.opacity_override is not None else pen.profile.opacity
        path_count += len(p.polylines)
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
        "path_count": path_count,
        "passes": passes,
    }


def _budget_block(layers: dict, plan_stats: dict, quality: QualityPreset) -> dict:
    limits = QUALITY_LIMITS[quality]
    paths = int(layers.get("path_count") or 0)
    max_paths = int(limits["max_paths"])
    strokes = int(plan_stats.get("stroke_count") or 0)
    eta = float(plan_stats.get("estimated_time_s") or 0)
    return {
        "path_count": paths,
        "max_paths": max_paths,
        "stroke_count": strokes,
        "estimated_time_s": eta,
        "quality": quality.value,
        "over_budget": paths > max_paths,
        "label": f"paths {paths} / {max_paths} · strokes {strokes} · ETA {eta:.1f}s · {quality.value}",
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
    extra: dict[str, Any] = dict(params_extra or {})
    paper_id, paper_color_hex = resolve_paper_color(
        extra.get("paper_id") or DEFAULT_PAPER_ID,
        extra.get("paper_color_hex"),
    )
    extra["paper_id"] = paper_id
    extra["paper_color_hex"] = paper_color_hex

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
        "params_extra": extra,
        "paper_mm": list(PAPER_MM[paper_enum]),
        "paper_id": paper_id,
        "paper_color_hex": paper_color_hex,
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
            **extra,
        },
        status=JobStatus.RENDERING,
    )
    save_job(job)
    try:
        from botdraw.portrait import (
            StrokeOrnamentParams,
            apply_pen_overrides,
            assign_pens,
            decorate_layered,
            resolve_portrait_vector,
        )

        palette = load_palette(palette_id)
        palette = apply_pen_overrides(palette, extra.get("pen_overrides"))

        cache_hit = False
        ingest_id = None
        if app == "portraitbot" or style_id.startswith("portrait_"):
            mode = extra.get("image_mode") or extra.get("image_type") or "photo"
            crop = extra.get("crop")
            auto_frame = extra.get("auto_frame", True)
            if isinstance(auto_frame, str):
                auto_frame = auto_frame.lower() not in ("0", "false", "no")
            pv, cache_hit = resolve_portrait_vector(
                image_path=image_path,
                mode=mode,
                quality=quality_enum.value,
                paper=paper_enum.value,
                crop=crop,
                reuse_ingest=bool(extra.get("reuse_ingest")),
                ingest_id=extra.get("ingest_id"),
                force_reingest=bool(extra.get("force_reingest")),
                auto_frame=bool(auto_frame) if crop is None else False,
                posterize_levels=extra.get("posterize_levels"),
                filter_speckle=extra.get("filter_speckle"),
                min_path_points=extra.get("min_path_points"),
                contrast=extra.get("contrast"),
                contour_simplify=extra.get("contour_simplify"),
                hatch_size=extra.get("hatch_size"),
                linedraw_jitter=extra.get("linedraw_jitter"),
                ensemble=extra.get("ensemble"),
                scan_mode=extra.get("scan_mode"),
            )
            pv = assign_pens(pv, palette, pen_map=extra.get("pen_map"))
            ingest_id = pv.ingest_id
            extra = {**extra, "portrait_vector": pv, "ingest_id": ingest_id}
            settings["ingest_id"] = ingest_id
            settings["ingest_cache_hit"] = cache_hit
            settings["crop"] = pv.crop.model_dump()

        engine = get_style(style_id)
        layered = engine.render(
            palette=palette,
            params=StyleParams(
                seed=seed,
                quality=quality_enum,
                density=density,
                extra=extra,
            ),
            paper=paper_enum,
            image_path=image_path,
        )

        # Drop non-serializable vector from settings copy
        settings_extra = {k: v for k, v in extra.items() if k != "portrait_vector"}
        settings["params_extra"] = settings_extra

        if app == "portraitbot" or style_id.startswith("portrait_"):
            orn = {
                "line_type": extra.get("line_type") or "solid",
                "line_spacing_mm": float(extra.get("line_spacing_mm") or 1.2),
                "pattern_period_mm": float(extra.get("pattern_period_mm") or 2.0),
                "pattern_amplitude_mm": float(extra.get("pattern_amplitude_mm") or 0.8),
                "dash_mm": float(extra.get("dash_mm") or 2.0),
                "gap_mm": float(extra.get("gap_mm") or 1.2),
                "ornament_target": extra.get("ornament_target") or "all",
                "max_paths": int(QUALITY_LIMITS[quality_enum]["max_paths"]),
            }
            layered = decorate_layered(layered, StrokeOrnamentParams.model_validate(orn))

        layered.meta = {
            **(layered.meta or {}),
            "paper_id": paper_id,
            "paper_color_hex": paper_color_hex,
            "ingest_cache_hit": cache_hit,
            "ingest_id": ingest_id,
        }

        layered = optimize_layered(layered)
        plan = compile_motion_plan(
            layered,
            palette,
            pen_up_speed_mm_s=pen_up_speed_mm_s,
            pen_down_speed_mm_s=pen_down_speed_mm_s,
        )
        out = artifact_dir(job.id)
        svg_path = save_svg(layered, palette, out / "art.svg", paper_color_hex=paper_color_hex)
        motion_path = out / "motion_plan.json"
        plan.save(motion_path)
        layers = layers_summary(layered, palette)
        budget = _budget_block(layers, plan.stats.model_dump(), quality_enum)
        layers["budget"] = budget
        layers["meta"] = {**(layers.get("meta") or {}), "budget": budget}
        (out / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
        (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        (out / "palette.json").write_text(palette.model_dump_json(indent=2), encoding="utf-8")
        payload = plan_to_emulator_payload(plan)
        payload["layers"] = layers
        payload["settings"] = settings
        payload["paper_color_hex"] = paper_color_hex
        payload["budget"] = budget
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
            "budget": budget,
        }
        (out / "export_pack.json").write_text(json.dumps(export_pack, indent=2), encoding="utf-8")
        return job, payload, layers
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        save_job(job)
        raise
