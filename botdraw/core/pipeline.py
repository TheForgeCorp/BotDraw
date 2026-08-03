"""End-to-end render → optimize → motion plan pipeline."""

from __future__ import annotations

from pathlib import Path

from botdraw.core.jobs import artifact_dir, save_job
from botdraw.core.models import JobRecord, JobStatus, PaperSize, QualityPreset, StyleParams
from botdraw.core.motion_plan import compile_motion_plan
from botdraw.core.optimize import optimize_layered
from botdraw.core.svg import save_svg
from botdraw.palettes import load_palette
from botdraw.plotter.emulator import plan_to_emulator_payload
from botdraw.styles import ensure_styles_loaded, get_style


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
) -> tuple[JobRecord, dict]:
    ensure_styles_loaded()
    job = JobRecord(
        app=app,
        style_id=style_id,
        seed=seed,
        quality=quality,
        palette_id=palette_id,
        paper=paper,
        params={"density": density, **(params_extra or {})},
        status=JobStatus.RENDERING,
    )
    save_job(job)
    try:
        palette = load_palette(palette_id)
        engine = get_style(style_id)
        layered = engine.render(
            palette=palette,
            params=StyleParams(seed=seed, quality=quality, density=density, extra=params_extra or {}),
            paper=paper,
            image_path=image_path,
        )
        layered = optimize_layered(layered)
        plan = compile_motion_plan(layered, palette)
        out = artifact_dir(job.id)
        svg_path = save_svg(layered, palette, out / "art.svg")
        motion_path = out / "motion_plan.json"
        plan.save(motion_path)
        payload_path = out / "emulator.json"
        payload = plan_to_emulator_payload(plan)
        payload_path.write_text(__import__("json").dumps(payload), encoding="utf-8")
        job.status = JobStatus.READY
        job.svg_path = str(svg_path)
        job.motion_path = str(motion_path)
        job.preview_path = str(payload_path)
        save_job(job)
        return job, payload
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        save_job(job)
        raise
