"""FastAPI application serving all BotDraw apps + emulator payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from botdraw.audio import render_audio_file, render_demo_tone
from botdraw.core.jobs import list_jobs, load_job
from botdraw.core.models import Orientation, PaperSize, QualityPreset
from botdraw.core.pipeline import render_job
from botdraw.handwriting import load_samples, render_with_clone, save_samples
from botdraw.letters import render_letter
from botdraw.llm import draft_wedding_letter, is_loaded, try_local_ollama, unload
from botdraw.palettes import calibrate_pen, create_palette, list_palette_ids, load_palette
from botdraw.plotter.axidraw import AxiDrawDriverStub
from botdraw.plotter.emulator import EmulatorDriver, plan_to_emulator_payload
from botdraw.core.motion_plan import MotionPlan
from botdraw.rdlab import render_experimental
from botdraw.styles import ensure_styles_loaded, list_styles

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="BotDraw", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


class RenderRequest(BaseModel):
    app: str = "genartbot"
    style_id: str
    palette_id: str = "default-6"
    paper: PaperSize = PaperSize.A4
    orientation: Orientation = Orientation.PORTRAIT
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED
    seed: int = 42
    density: float = 1.0
    pen_up_speed_mm_s: float = 100.0
    pen_down_speed_mm_s: float = 25.0
    params_extra: dict[str, Any] = {}


class PaletteSaveRequest(BaseModel):
    id: str
    name: str
    paper_notes: str = ""
    pens: list[dict[str, Any]]


class LetterRequest(BaseModel):
    names: str = "A & B"
    language: str = "en"
    era: str = "90s"
    mood: str = "romantic"
    facts: str = ""
    guest_quote: Optional[str] = None
    highlight: bool = True
    palette_id: str = "wedding-highlight"
    seed: int = 7


class HandwritingSample(BaseModel):
    user_id: str
    glyphs: dict[str, list[list[list[float]]]]


class CalibrateRequest(BaseModel):
    palette_id: str
    pen_id: str
    width_mm: Optional[float] = None
    color_hex: Optional[str] = None
    opacity: Optional[float] = None
    nib_type: Optional[str] = None


@app.on_event("startup")
def _startup():
    ensure_styles_loaded()


@app.get("/", response_class=HTMLResponse)
def index():
    path = WEB_DIR / "index.html"
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "llm_loaded": is_loaded()}


@app.get("/api/styles")
def api_styles(category: Optional[str] = None):
    ensure_styles_loaded()
    return list_styles(category)


@app.get("/api/palettes")
def api_palettes():
    return [{"id": pid, **load_palette(pid).model_dump()} for pid in list_palette_ids()]


@app.post("/api/palettes/calibrate")
def api_calibrate(body: CalibrateRequest):
    return calibrate_pen(
        body.palette_id,
        body.pen_id,
        width_mm=body.width_mm,
        color_hex=body.color_hex,
        opacity=body.opacity,
        nib_type=body.nib_type,
    )


@app.post("/api/palettes/save")
def api_palette_save(body: PaletteSaveRequest):
    palette = create_palette(
        body.id,
        body.name,
        body.pens,
        paper_notes=body.paper_notes,
    )
    return palette.model_dump()


@app.post("/api/render")
def api_render(body: RenderRequest):
    job, payload, layers = render_job(
        app=body.app,
        style_id=body.style_id,
        palette_id=body.palette_id,
        paper=body.paper,
        orientation=body.orientation,
        quality=body.quality,
        seed=body.seed,
        density=body.density,
        params_extra=body.params_extra,
        pen_up_speed_mm_s=body.pen_up_speed_mm_s,
        pen_down_speed_mm_s=body.pen_down_speed_mm_s,
    )
    return {"job": job.model_dump(), "emulator": payload, "layers": layers}


@app.post("/api/render/upload")
async def api_render_upload(
    style_id: str = Form(...),
    app_name: str = Form("portraitbot"),
    palette_id: str = Form("default-6"),
    quality: str = Form("booth-balanced"),
    paper: str = Form("A4"),
    orientation: str = Form("portrait"),
    seed: int = Form(42),
    density: float = Form(1.0),
    pen_up_speed_mm_s: float = Form(100.0),
    pen_down_speed_mm_s: float = Form(25.0),
    file: UploadFile = File(...),
):
    from botdraw.core.jobs import artifact_dir
    from uuid import uuid4

    tmp = artifact_dir(uuid4().hex[:8]) / (file.filename or "upload.png")
    tmp.write_bytes(await file.read())
    job, payload, layers = render_job(
        app=app_name,
        style_id=style_id,
        palette_id=palette_id,
        paper=PaperSize(paper),
        orientation=Orientation(orientation),
        quality=QualityPreset(quality),
        seed=seed,
        density=density,
        image_path=str(tmp),
        pen_up_speed_mm_s=pen_up_speed_mm_s,
        pen_down_speed_mm_s=pen_down_speed_mm_s,
    )
    return {"job": job.model_dump(), "emulator": payload, "layers": layers}


@app.post("/api/letters/draft")
def api_letter_draft(body: LetterRequest):
    try_local_ollama()
    draft = draft_wedding_letter(
        names=body.names,
        language=body.language,
        era=body.era,
        mood=body.mood,
        facts=body.facts,
        guest_quote=body.guest_quote,
    )
    unload()
    layered = render_letter(
        draft["body"],
        palette_id=body.palette_id,
        language=body.language,
        guest_quote=body.guest_quote,
        highlight_words=["forever", "heart", "love"] if body.highlight else None,
        seed=body.seed,
    )
    from botdraw.core.optimize import optimize_layered
    from botdraw.core.motion_plan import compile_motion_plan
    from botdraw.core.jobs import artifact_dir, save_job
    from botdraw.core.models import JobRecord, JobStatus
    from botdraw.core.svg import save_svg
    from botdraw.core.pipeline import layers_summary

    palette = load_palette(body.palette_id)
    layered = optimize_layered(layered)
    plan = compile_motion_plan(layered, palette)
    layers = layers_summary(layered, palette)
    settings = {
        "app": "lettersbot",
        "style_id": "letter",
        "palette_id": body.palette_id,
        "seed": body.seed,
        "language": body.language,
        "era": body.era,
        "mood": body.mood,
        "names": body.names,
        "guest_quote": body.guest_quote,
        "highlight": body.highlight,
    }
    job = JobRecord(app="lettersbot", style_id="letter", status=JobStatus.READY, seed=body.seed, palette_id=body.palette_id)
    out = artifact_dir(job.id)
    job.svg_path = str(save_svg(layered, palette, out / "art.svg"))
    plan.save(out / "motion_plan.json")
    payload = plan_to_emulator_payload(plan)
    payload["layers"] = layers
    payload["settings"] = settings
    (out / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (out / "emulator.json").write_text(json.dumps(payload), encoding="utf-8")
    (out / "export_pack.json").write_text(
        json.dumps(
            {
                "settings": settings,
                "draft": draft,
                "job": job.model_dump(),
                "layers": layers,
                "palette": json.loads(palette.model_dump_json()),
                "motion_plan": plan.to_dict(),
                "stats": plan.stats.model_dump(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    job.motion_path = str(out / "motion_plan.json")
    job.preview_path = str(out / "emulator.json")
    save_job(job)
    return {"draft": draft, "job": job.model_dump(), "emulator": payload, "layers": layers, "settings": settings}


@app.post("/api/handwriting/samples")
def api_hw_samples(body: HandwritingSample):
    path = save_samples(body.user_id, body.glyphs)
    return {"ok": True, "path": str(path)}


@app.get("/api/handwriting/{user_id}")
def api_hw_get(user_id: str):
    return load_samples(user_id)


@app.post("/api/handwriting/render")
def api_hw_render(user_id: str = "demo", text: str = "Hello"):
    from botdraw.core.optimize import optimize_layered
    from botdraw.core.motion_plan import compile_motion_plan
    from botdraw.core.jobs import artifact_dir, save_job
    from botdraw.core.models import JobRecord, JobStatus
    from botdraw.core.pipeline import layers_summary
    from botdraw.core.svg import save_svg

    layered = render_with_clone(text, user_id)
    palette = load_palette("wedding-highlight")
    layered = optimize_layered(layered)
    plan = compile_motion_plan(layered, palette)
    layers = layers_summary(layered, palette)
    settings = {"app": "handwriting", "style_id": "clone", "user_id": user_id, "text": text, "palette_id": "wedding-highlight"}
    job = JobRecord(app="handwriting", style_id="clone", status=JobStatus.READY, palette_id="wedding-highlight")
    out = artifact_dir(job.id)
    job.svg_path = str(save_svg(layered, palette, out / "art.svg"))
    plan.save(out / "motion_plan.json")
    payload = plan_to_emulator_payload(plan)
    payload["layers"] = layers
    payload["settings"] = settings
    (out / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (out / "emulator.json").write_text(json.dumps(payload), encoding="utf-8")
    (out / "export_pack.json").write_text(
        json.dumps(
            {
                "settings": settings,
                "job": job.model_dump(),
                "layers": layers,
                "palette": json.loads(palette.model_dump_json()),
                "motion_plan": plan.to_dict(),
                "stats": plan.stats.model_dump(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    job.preview_path = str(out / "emulator.json")
    job.motion_path = str(out / "motion_plan.json")
    save_job(job)
    return {"job": job.model_dump(), "emulator": payload, "layers": layers, "settings": settings}


def _audio_job(layered, *, source: str = "demo"):
    from botdraw.core.optimize import optimize_layered
    from botdraw.core.motion_plan import compile_motion_plan
    from botdraw.core.jobs import artifact_dir, save_job
    from botdraw.core.models import JobRecord, JobStatus
    from botdraw.core.pipeline import layers_summary
    from botdraw.core.svg import save_svg

    palette = load_palette("default-6")
    layered = optimize_layered(layered)
    plan = compile_motion_plan(layered, palette)
    layers = layers_summary(layered, palette)
    settings = {"app": "audio", "style_id": "audio", "palette_id": "default-6", "source": source}
    job = JobRecord(app="audio", style_id="audio", status=JobStatus.READY, palette_id="default-6")
    out = artifact_dir(job.id)
    job.svg_path = str(save_svg(layered, palette, out / "art.svg"))
    plan.save(out / "motion_plan.json")
    payload = plan_to_emulator_payload(plan)
    payload["layers"] = layers
    payload["settings"] = settings
    (out / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (out / "emulator.json").write_text(json.dumps(payload), encoding="utf-8")
    (out / "export_pack.json").write_text(
        json.dumps(
            {
                "settings": settings,
                "job": job.model_dump(),
                "layers": layers,
                "palette": json.loads(palette.model_dump_json()),
                "motion_plan": plan.to_dict(),
                "stats": plan.stats.model_dump(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    job.preview_path = str(out / "emulator.json")
    job.motion_path = str(out / "motion_plan.json")
    save_job(job)
    return {"job": job.model_dump(), "emulator": payload, "layers": layers, "settings": settings}


@app.post("/api/audio/demo")
def api_audio_demo():
    return _audio_job(render_demo_tone(), source="demo-tone")


@app.post("/api/audio/upload")
async def api_audio_upload(file: UploadFile = File(...)):
    from botdraw.core.jobs import artifact_dir
    from uuid import uuid4

    tmp = artifact_dir(uuid4().hex[:8]) / (file.filename or "audio.wav")
    tmp.write_bytes(await file.read())
    return _audio_job(render_audio_file(tmp), source=file.filename or "upload.wav")


@app.post("/api/rdlab/render")
async def api_rdlab(
    style_id: str = Form("spiral"),
    rpm: float = Form(3.0),
    seed: int = Form(42),
    palette_id: str = Form("default-6"),
    quality: str = Form("booth-balanced"),
    density: float = Form(1.0),
    orientation: str = Form("portrait"),
    file: UploadFile | None = File(None),
):
    from botdraw.core.jobs import artifact_dir, save_job
    from botdraw.core.models import JobRecord, JobStatus
    from botdraw.core.svg import save_svg
    from uuid import uuid4

    image_path = None
    if file is not None and file.filename:
        tmp = artifact_dir(uuid4().hex[:8]) / file.filename
        tmp.write_bytes(await file.read())
        image_path = str(tmp)

    layered, plan = render_experimental(
        style_id,
        palette_id=palette_id,
        seed=seed,
        rpm=rpm,
        image_path=image_path,
        quality=QualityPreset(quality),
        density=density,
        orientation=Orientation(orientation),
    )
    palette = load_palette(palette_id)
    from botdraw.core.pipeline import layers_summary

    layers = layers_summary(layered, palette)
    job = JobRecord(app="rdlab", style_id=style_id, status=JobStatus.READY, seed=seed, palette_id=palette_id)
    out = artifact_dir(job.id)
    job.svg_path = str(save_svg(layered, palette, out / "art.svg"))
    plan.save(out / "motion_plan.json")
    settings = {
        "app": "rdlab",
        "style_id": style_id,
        "rpm": rpm,
        "seed": seed,
        "palette_id": palette_id,
        "quality": quality,
        "density": density,
        "orientation": orientation,
        "image_path": image_path,
    }
    payload = plan_to_emulator_payload(plan)
    payload["layers"] = layers
    payload["settings"] = settings
    (out / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (out / "emulator.json").write_text(json.dumps(payload), encoding="utf-8")
    (out / "export_pack.json").write_text(
        json.dumps(
            {
                "settings": settings,
                "job": job.model_dump(),
                "layers": layers,
                "palette": json.loads(palette.model_dump_json()),
                "motion_plan": plan.to_dict(),
                "stats": plan.stats.model_dump(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    job.preview_path = str(out / "emulator.json")
    job.motion_path = str(out / "motion_plan.json")
    save_job(job)
    return {"job": job.model_dump(), "emulator": payload, "layers": layers, "settings": settings}


@app.post("/api/plot/stub")
def api_plot_stub(job_id: str):
    job = load_job(job_id)
    if not job.motion_path:
        raise HTTPException(404, "No motion plan")
    plan = MotionPlan.load(job.motion_path)
    stub = AxiDrawDriverStub()
    stub.connect()
    result = stub.plot(plan)
    emu = EmulatorDriver()
    emu.connect()
    emu_result = emu.plot(plan, speed_multiplier=50)
    return {"stub": result, "emulator_run": {"elapsed_s": emu_result["elapsed_s"], "segments": emu_result["segment_count"]}}


@app.get("/api/jobs")
def api_jobs():
    return [j.model_dump() for j in list_jobs()]


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = load_job(job_id)
    payload = None
    layers = None
    settings = None
    out = Path(job.preview_path).parent if job.preview_path else None
    if job.preview_path and Path(job.preview_path).exists():
        payload = json.loads(Path(job.preview_path).read_text(encoding="utf-8"))
    if out and (out / "layers.json").exists():
        layers = json.loads((out / "layers.json").read_text(encoding="utf-8"))
    if out and (out / "settings.json").exists():
        settings = json.loads((out / "settings.json").read_text(encoding="utf-8"))
    return {"job": job.model_dump(), "emulator": payload, "layers": layers, "settings": settings}


@app.get("/api/jobs/{job_id}/svg")
def api_job_svg(job_id: str):
    job = load_job(job_id)
    if not job.svg_path or not Path(job.svg_path).exists():
        raise HTTPException(404, "SVG missing")
    return FileResponse(job.svg_path, media_type="image/svg+xml", filename=f"{job_id}.svg")


@app.get("/api/jobs/{job_id}/export")
def api_job_export(job_id: str):
    job = load_job(job_id)
    out = Path(job.preview_path).parent if job.preview_path else None
    if not out or not (out / "export_pack.json").exists():
        raise HTTPException(404, "Export pack missing — re-render the job")
    return JSONResponse(json.loads((out / "export_pack.json").read_text(encoding="utf-8")))


@app.get("/api/jobs/{job_id}/layers")
def api_job_layers(job_id: str):
    job = load_job(job_id)
    out = Path(job.preview_path).parent if job.preview_path else None
    if not out or not (out / "layers.json").exists():
        raise HTTPException(404, "Layers missing")
    return json.loads((out / "layers.json").read_text(encoding="utf-8"))


@app.get("/api/jobs/{job_id}/motion")
def api_job_motion(job_id: str):
    job = load_job(job_id)
    if not job.motion_path or not Path(job.motion_path).exists():
        raise HTTPException(404, "Motion plan missing")
    return json.loads(Path(job.motion_path).read_text(encoding="utf-8"))
