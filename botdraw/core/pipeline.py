"""End-to-end render → optimize → motion plan pipeline."""

from __future__ import annotations

import json
from typing import Any

from botdraw.core.jobs import artifact_dir, load_job, save_job
from botdraw.core.models import (
    PAPER_MM,
    QUALITY_LIMITS,
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
                "role": p.stable_role(),
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


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _ai_review_mode(extra: dict[str, Any], *, quality: str | None = None) -> str:
    from botdraw.portrait.claude_review import resolve_ai_review_mode

    return resolve_ai_review_mode(
        extra.get("ai_review"),
        quality=quality or extra.get("quality"),
    )


def _load_rgb_for_review(image_path: str | None) -> Any:
    import numpy as np
    from PIL import Image

    from botdraw.styles.image_utils import synthetic_portrait

    if image_path:
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        return np.asarray(img, dtype=np.float32)
    return synthetic_portrait(512).astype(np.float32)


def _apply_ai_scene_review(
    extra: dict[str, Any],
    *,
    image_path: str | None,
    quality: str | None = None,
) -> dict[str, Any]:
    """Merge PortraitScene knobs into extra. Fail closed on errors."""
    try:
        from botdraw.portrait.claude_review import maybe_review_and_merge_knobs, resolve_ai_review_mode

        mode = resolve_ai_review_mode(extra.get("ai_review"), quality=quality)
        rgb = _load_rgb_for_review(image_path)
        _rgb2, merged = maybe_review_and_merge_knobs(
            rgb, dict(extra), enabled=True, mode=mode, quality=quality
        )
        return merged
    except Exception:
        out = dict(extra)
        from botdraw.portrait.claude_review import resolve_ai_review_mode

        out["ai_review"] = resolve_ai_review_mode(extra.get("ai_review"), quality=quality)
        out["ai_review_status"] = "scene_failed"
        return out


def _layered_preview_png(layered: LayeredSVG, palette: PaletteSet, paper_color_hex: str) -> bytes | None:
    """Rasterize layered SVG for critique. Prefer cairosvg; else stroke raster."""
    try:
        from botdraw.core.svg import layered_to_svg_string

        svg = layered_to_svg_string(layered, palette, paper_color_hex=paper_color_hex)
    except Exception:
        try:
            from botdraw.core.svg import layered_to_svg_string

            svg = layered_to_svg_string(layered, palette)
        except Exception:
            return None
    try:
        import cairosvg

        return cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=720)
    except Exception:
        pass
    # Fallback: crude polyline raster
    try:
        import numpy as np
        from PIL import Image, ImageDraw

        w, h = 720, int(720 * layered.height_mm / max(layered.width_mm, 1e-3))
        im = Image.new("RGB", (w, h), paper_color_hex or "#f7f1e8")
        draw = ImageDraw.Draw(im)
        sx = w / max(layered.width_mm, 1e-3)
        sy = h / max(layered.height_mm, 1e-3)
        for pas in layered.passes:
            try:
                pen = palette.pen_by_id(pas.pen_id)
                color = pen.color_hex
            except Exception:
                color = "#222222"
            for poly in pas.polylines:
                if len(poly.points) < 2:
                    continue
                pts = [(p[0] * sx, p[1] * sy) for p in poly.points]
                draw.line(pts, fill=color, width=1)
        import io

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _apply_ai_structure_after_ingest(extra: dict[str, Any]) -> dict[str, Any]:
    """Studio turn 2: critique ingest structure preview (not restyle PNG)."""
    try:
        import numpy as np

        from botdraw.portrait.claude_review import apply_structure_critique_to_knobs
        from botdraw.portrait.vision_loop import structure_preview_png

        pv = extra.get("portrait_vector")
        if pv is None or int(extra.get("ai_vision_turn") or 0) >= 2:
            return extra
        png = structure_preview_png(pv)
        source = np.asarray(pv.rgb, dtype=np.float32)
        return apply_structure_critique_to_knobs(source, png, dict(extra), turn=2)
    except Exception:
        out = dict(extra)
        out["ai_vision_turn"] = max(2, int(extra.get("ai_vision_turn") or 0))
        out["ai_review_status"] = "structure_unavailable"
        return out


def _apply_ai_critique_once(
    extra: dict[str, Any],
    *,
    layered: LayeredSVG,
    palette: PaletteSet,
    paper_color_hex: str,
) -> dict[str, Any] | None:
    """Turn-3 confirm critique on restyle preview; restyle knobs only (no re-ingest)."""
    try:
        from botdraw.portrait.claude_review import (
            VISION_MAX_TURNS,
            critique_render,
            critique_to_render_knobs,
        )

        pv = extra.get("portrait_vector")
        if pv is None:
            return None
        png = _layered_preview_png(layered, palette, paper_color_hex)
        if not png:
            return None
        import numpy as np

        source = np.asarray(pv.rgb, dtype=np.float32)
        style = str(extra.get("style_id") or layered.meta.get("portrait_style") or "portrait_linework")
        # Confirm is always turn 3 in the 3-turn plan (structure already applied as turn 2)
        turn = max(3, int(extra.get("ai_vision_turn") or 2) + 1)
        max_turns = int(extra.get("ai_vision_max_turns") or VISION_MAX_TURNS)
        if turn > max_turns:
            out = dict(extra)
            out["ai_critique_applied"] = True
            return out
        critique = critique_render(
            source,
            png,
            style_id=style,
            turn=turn,
            structure=False,
        )
        if critique is None:
            out = dict(extra)
            out["ai_review_status"] = "critique_unavailable"
            out["ai_critique_applied"] = True
            out["ai_vision_turn"] = turn
            return out
        # Turn 3 confirm: restyle knobs only — never re-ingest
        critique.actions.force_reingest = False
        knobs = critique_to_render_knobs(critique)
        knobs.pop("force_reingest", None)
        history = list(extra.get("ai_vision_history") or [])
        history.append(
            {
                "turn": turn,
                "kind": "confirm",
                "overall": critique.overall,
                "summary": critique.summary,
                "force_reingest": False,
                "actions": critique.actions.model_dump(),
            }
        )
        by_turn = dict(extra.get("ai_critique_by_turn") or {})
        by_turn[str(turn)] = critique.model_dump()
        out = {
            **extra,
            **knobs,
            "ai_vision_turn": turn,
            "ai_vision_history": history,
            "ai_critique": critique.model_dump(),
            "ai_critique_by_turn": by_turn,
            "ai_review_status": "confirm",
            "reuse_ingest": True,
            "ingest_id": getattr(pv, "ingest_id", None),
        }
        out.pop("force_reingest", None)
        # One optional restyle adjust, then done
        actionable = any(
            [
                knobs.get("style_id") and knobs.get("style_id") != style,
                knobs.get("density_mul") and abs(float(knobs["density_mul"]) - 1.0) > 0.05,
                knobs.get("hatch_budget_mul") and abs(float(knobs["hatch_budget_mul"]) - 1.0) > 0.05,
            ]
        )
        if actionable and not extra.get("ai_confirm_restyle_done"):
            out["ai_critique_applied"] = False
            out["ai_confirm_restyle_done"] = True
        else:
            out["ai_critique_applied"] = True
        return out
    except Exception:
        return None


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
    settings_patch: dict | None = None,
) -> tuple[JobRecord, dict, dict]:
    """Optimize a pre-built LayeredSVG and write job artifacts (same shape as render_job)."""
    paper_enum = paper if isinstance(paper, PaperSize) else PaperSize(paper)
    orientation_enum = orientation if isinstance(orientation, Orientation) else Orientation(orientation)
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
    extra: dict[str, Any] = dict(params_extra or {})
    serial_extra = {k: v for k, v in extra.items() if k != "portrait_vector"}
    paper_id, paper_color_hex = resolve_paper_color(
        extra.get("paper_id") or DEFAULT_PAPER_ID,
        extra.get("paper_color_hex"),
    )
    extra["paper_id"] = paper_id
    extra["paper_color_hex"] = paper_color_hex
    serial_extra["paper_id"] = paper_id
    serial_extra["paper_color_hex"] = paper_color_hex

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
        "params_extra": serial_extra,
        "paper_mm": list(paper_dims(paper_enum, orientation_enum)),
        "paper_id": paper_id,
        "paper_color_hex": paper_color_hex,
    }
    if settings_patch:
        settings.update(settings_patch)
        settings["params_extra"] = serial_extra
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
                **serial_extra,
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
                    **serial_extra,
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
                **serial_extra,
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
        svg_path = save_svg(layered, palette, out / "art.svg", paper_color_hex=paper_color_hex)
        motion_path = out / "motion_plan.json"
        plan.save(motion_path)
        layers = layers_summary(layered, palette)
        budget = _budget_block(layers, plan.stats.model_dump(), quality_enum)
        layers["budget"] = budget
        layers["meta"] = {**(layers.get("meta") or {}), "budget": budget}
        (out / "layered.json").write_text(layered.model_dump_json(indent=2), encoding="utf-8")
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
        "orientation": orientation_enum.value,
        "quality": quality_enum.value,
        "seed": seed,
        "density": density,
        "pen_up_speed_mm_s": pen_up_speed_mm_s,
        "pen_down_speed_mm_s": pen_down_speed_mm_s,
        "image_path": image_path,
        "params_extra": extra,
        "paper_mm": list(paper_dims(paper_enum, orientation_enum)),
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
        orientation=orientation_enum,
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
        from botdraw.portrait.claude_review import (
            ai_review_wants_critique,
            ai_review_wants_scene,
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
            ai_mode = _ai_review_mode(extra, quality=quality_enum.value)
            extra["ai_review"] = ai_mode
            # Pre-ingest scene review → knobs (live + studio; once only)
            if (
                ai_review_wants_scene(ai_mode)
                and not extra.get("ai_critique_applied")
                and not extra.get("ai_vision_turn")
            ):
                extra = _apply_ai_scene_review(
                    extra, image_path=image_path, quality=quality_enum.value
                )
                crop = extra.get("crop", crop)
                auto_frame = extra.get("auto_frame", auto_frame)
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
                line_source=extra.get("line_source"),
                max_tone_code=extra.get("max_tone_code"),
                suppress_background=extra.get("suppress_background"),
                protect_subjects=extra.get("protect_subjects"),
                orientation_deg=extra.get("orientation_deg"),
                ai_scene=extra.get("ai_scene"),
            )
            pv = assign_pens(pv, palette, pen_map=extra.get("pen_map"))
            ingest_id = pv.ingest_id
            extra = {**extra, "portrait_vector": pv, "ingest_id": ingest_id}
            extra.pop("force_reingest", None)
            settings["ingest_id"] = ingest_id
            settings["ingest_cache_hit"] = cache_hit
            settings["crop"] = pv.crop.model_dump()
            if extra.get("ai_scene"):
                settings["ai_scene"] = extra["ai_scene"]

            # Studio turn 2: structure critique on ingest preview (at most one re-ingest)
            if (
                ai_review_wants_critique(ai_mode)
                and not extra.get("ai_critique_applied")
                and int(extra.get("ai_vision_turn") or 0) < 2
            ):
                extra = _apply_ai_structure_after_ingest(extra)
                if extra.get("force_reingest"):
                    extra["ai_reingest_count"] = int(extra.get("ai_reingest_count") or 0) + 1
                    extra.pop("force_reingest", None)
                    pv, cache_hit = resolve_portrait_vector(
                        image_path=image_path,
                        mode=mode,
                        quality=quality_enum.value,
                        paper=paper_enum.value,
                        crop=extra.get("crop", crop),
                        reuse_ingest=False,
                        ingest_id=None,
                        force_reingest=True,
                        auto_frame=bool(extra.get("auto_frame", auto_frame))
                        if extra.get("crop", crop) is None
                        else False,
                        posterize_levels=extra.get("posterize_levels"),
                        filter_speckle=extra.get("filter_speckle"),
                        min_path_points=extra.get("min_path_points"),
                        contrast=extra.get("contrast"),
                        contour_simplify=extra.get("contour_simplify"),
                        hatch_size=extra.get("hatch_size"),
                        linedraw_jitter=extra.get("linedraw_jitter"),
                        ensemble=extra.get("ensemble"),
                        scan_mode=extra.get("scan_mode"),
                        line_source=extra.get("line_source"),
                        max_tone_code=extra.get("max_tone_code"),
                        suppress_background=extra.get("suppress_background"),
                        protect_subjects=extra.get("protect_subjects"),
                        orientation_deg=extra.get("orientation_deg"),
                        ai_scene=extra.get("ai_scene"),
                    )
                    pv = assign_pens(pv, palette, pen_map=extra.get("pen_map"))
                    ingest_id = pv.ingest_id
                    extra = {**extra, "portrait_vector": pv, "ingest_id": ingest_id}
                    settings["ingest_id"] = ingest_id
                    settings["ingest_cache_hit"] = cache_hit
                    settings["crop"] = pv.crop.model_dump()

        # Density may be nudged by critique hatch_budget_mul / density_mul
        render_density = float(density) * float(extra.get("density_mul") or 1.0)
        if extra.get("hatch_budget_mul"):
            render_density *= float(extra["hatch_budget_mul"]) ** 0.5
        active_style = str(extra.get("style_id") or style_id)

        engine = get_style(active_style)
        layered = engine.render(
            palette=palette,
            params=StyleParams(
                seed=seed,
                quality=quality_enum,
                density=render_density,
                extra=extra,
            ),
            paper=paper_enum,
            orientation=orientation_enum,
            image_path=image_path,
        )

        if extra.get("pass_overrides"):
            from botdraw.portrait.customization import apply_pass_overrides

            layered = apply_pass_overrides(layered, palette, extra.get("pass_overrides"))

        # Studio turn 3: confirm critique on restyle preview (no re-ingest)
        if (
            (app == "portraitbot" or style_id.startswith("portrait_"))
            and ai_review_wants_critique(_ai_review_mode(extra, quality=quality_enum.value))
            and not extra.get("ai_critique_applied")
            and int(extra.get("ai_vision_turn") or 0) >= 2
        ):
            crit_extra = _apply_ai_critique_once(
                extra,
                layered=layered,
                palette=palette,
                paper_color_hex=paper_color_hex,
            )
            if crit_extra is not None:
                redo = bool(not crit_extra.get("ai_critique_applied"))
                extra = {
                    **crit_extra,
                    "ai_review": "studio",
                    "ai_review_status": crit_extra.get("ai_review_status") or "confirm",
                }
                if redo:
                    extra.pop("portrait_vector", None)
                    return render_job(
                        app=app,
                        style_id=str(extra.get("style_id") or style_id),
                        palette_id=palette_id,
                        paper=paper_enum,
                        quality=quality_enum,
                        seed=seed,
                        density=density,
                        image_path=image_path,
                        params_extra=extra,
                        pen_up_speed_mm_s=pen_up_speed_mm_s,
                        pen_down_speed_mm_s=pen_down_speed_mm_s,
                    )

        # Drop non-serializable vector from settings copy
        settings_extra = {k: v for k, v in extra.items() if k != "portrait_vector"}
        settings["params_extra"] = settings_extra
        if extra.get("ai_critique"):
            settings["ai_critique"] = extra["ai_critique"]

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

        ai_mode_final = _ai_review_mode(extra, quality=quality_enum.value)
        layered.meta = {
            **(layered.meta or {}),
            "paper_id": paper_id,
            "paper_color_hex": paper_color_hex,
            "ingest_cache_hit": cache_hit,
            "ingest_id": ingest_id,
            "ai_review": ai_mode_final,
            "ai_review_status": extra.get("ai_review_status"),
            "ai_scene_summary": (extra.get("ai_scene") or {}).get("summary"),
            "ai_critique_summary": (extra.get("ai_critique") or {}).get("summary"),
            "ai_vision_turn": extra.get("ai_vision_turn"),
            "ai_vision_history": extra.get("ai_vision_history"),
            "ai_critique_by_turn": extra.get("ai_critique_by_turn"),
        }

        if extra.get("ai_scene"):
            settings["ai_scene"] = extra["ai_scene"]
        if extra.get("ai_vision_history"):
            settings["ai_vision_history"] = extra["ai_vision_history"]
        if extra.get("ai_critique_by_turn"):
            settings["ai_critique_by_turn"] = extra["ai_critique_by_turn"]
        if extra.get("ai_vision_turn") is not None:
            settings["ai_vision_turn"] = extra["ai_vision_turn"]

        if extra.get("ai_scene"):
            try:
                (artifact_dir(job.id) / "ai_scene.json").write_text(
                    json.dumps(extra["ai_scene"], indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        by_turn = extra.get("ai_critique_by_turn") or {}
        if by_turn:
            try:
                for t_key, critique_payload in by_turn.items():
                    (artifact_dir(job.id) / f"ai_critique_t{t_key}.json").write_text(
                        json.dumps(critique_payload, indent=2), encoding="utf-8"
                    )
            except Exception:
                pass
        if extra.get("ai_critique"):
            try:
                turn = int(extra.get("ai_vision_turn") or 2)
                if str(turn) not in by_turn:
                    (artifact_dir(job.id) / f"ai_critique_t{turn}.json").write_text(
                        json.dumps(extra["ai_critique"], indent=2), encoding="utf-8"
                    )
                (artifact_dir(job.id) / "ai_critique.json").write_text(
                    json.dumps(extra["ai_critique"], indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        if extra.get("ai_vision_history"):
            try:
                (artifact_dir(job.id) / "ai_vision_history.json").write_text(
                    json.dumps(extra["ai_vision_history"], indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        return render_from_layered(
            app=app,
            style_id=str(extra.get("style_id") or style_id),
            layered=layered,
            palette_id=palette_id,
            paper=paper_enum,
            orientation=orientation_enum,
            quality=quality_enum,
            seed=seed,
            density=density,
            image_path=image_path,
            params_extra=settings_extra,
            pen_up_speed_mm_s=pen_up_speed_mm_s,
            pen_down_speed_mm_s=pen_down_speed_mm_s,
            job_id=job.id,
            settings_patch=settings,
        )
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        save_job(job)
        raise
