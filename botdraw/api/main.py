"""FastAPI application serving all BotDraw apps + emulator payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from botdraw.audio import render_audio_file, render_demo_tone
from botdraw.core.jobs import list_jobs, load_job
from botdraw.core.models import PaperSize, QualityPreset
from botdraw.core.pipeline import render_job
from botdraw.handwriting import load_samples, render_with_clone, save_samples
from botdraw.letters import (
    LetterLayerSpec,
    LineGeom,
    Margins,
    SnapSpec,
    render_letter,
    render_letter_layers,
)
from botdraw.letters.fonts import list_fonts
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
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED
    seed: int = 42
    density: float = 1.0
    pen_up_speed_mm_s: float = 100.0
    pen_down_speed_mm_s: float = 25.0
    params_extra: dict[str, Any] = {}
    paper_id: Optional[str] = None
    paper_color_hex: Optional[str] = None
    reuse_ingest: bool = False
    ingest_id: Optional[str] = None
    force_reingest: bool = False
    crop: Optional[dict[str, Any]] = None


class PaletteSaveRequest(BaseModel):
    id: str
    name: str
    paper_notes: str = ""
    pens: list[dict[str, Any]]


class MarginsModel(BaseModel):
    left: float = 18.0
    top: float = 18.0
    right: float = 18.0
    bottom: float = 18.0


class LineGeomModel(BaseModel):
    x0_mm: float = 20.0
    y0_mm: float = 40.0
    x1_mm: float = 120.0
    y1_mm: float = 40.0
    style: str = "solid"
    dash_mm: float = 2.0
    gap_mm: float = 1.2
    width_mm: Optional[float] = None


class SnapModel(BaseModel):
    target_layer_id: Optional[str] = None
    span_index: Optional[int] = None
    role: str = "underline"


class LetterLayerModel(BaseModel):
    id: str = "layer-0"
    name: str = "Ink"
    body: str = ""
    font_name: str = "simplex"
    size_mm: float = 4.5
    pen_id: str = "ink"
    language: str = "en"
    translate_from_en: bool = False
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    kind: str = "ink"
    tracking: float = 0.15
    humanize: float = 0.08
    line_height: Optional[float] = None
    highlight_words: list[str] = []
    draw_mode: str = "text"
    leading_variation: float = 0.12
    line_angle_deg: float = 0.0
    line: Optional[LineGeomModel] = None
    placement: str = "freehand"
    snap: Optional[SnapModel] = None


class LetterRequest(BaseModel):
    names: str = "A & B"
    language: str = "en"
    era: str = "90s"
    mood: str = "romantic"
    facts: str = ""
    guest_quote: Optional[str] = None
    highlight: bool = True
    highlight_words: Optional[list[str]] = None
    palette_id: str = "wedding-highlight"
    seed: int = 7
    paper: str = "A5"
    letter_type: str = "personal"
    # Dev Lab default: skip Ollama. Booth / AI draft sets use_llm=true.
    use_llm: bool = False
    # If set, skip drafting and vectorize this body only (fast path).
    body: Optional[str] = None
    # Letters are already reading-order; greedy linesort is optional.
    optimize: bool = False
    size_mm: float = 4.5
    line_height: Optional[float] = None
    tracking: float = 0.15
    humanize: float = 0.08
    orientation: str = "portrait"
    font_name: str = "simplex"
    margins: Optional[MarginsModel] = None
    layers: Optional[list[LetterLayerModel]] = None


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


class LineSaveRequest(BaseModel):
    id: str
    name: str
    line_type: str = "solid"
    line_spacing_mm: float = 1.2
    pattern_period_mm: float = 2.0
    pattern_amplitude_mm: float = 0.8
    dash_mm: float = 2.0
    gap_mm: float = 1.2
    ornament_target: str = "all"
    notes: str = ""


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


@app.get("/api/papers")
def api_papers():
    from botdraw.paper import list_papers

    return list_papers()


class PaperSaveRequest(BaseModel):
    id: str
    name: str
    color_hex: str = "#f7f1e8"
    finish: str = "matte"
    size_hint: Optional[str] = "A4"
    notes: str = ""


@app.post("/api/papers/save")
def api_paper_save(body: PaperSaveRequest):
    from botdraw.paper import PaperStock, save_paper

    stock = save_paper(
        PaperStock(
            id=body.id,
            name=body.name,
            color_hex=body.color_hex,
            finish=body.finish,
            size_hint=body.size_hint,
            notes=body.notes,
        )
    )
    return stock.model_dump()


@app.delete("/api/papers/{paper_id}")
def api_paper_delete(paper_id: str):
    from botdraw.paper import delete_paper

    try:
        delete_paper(paper_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "id": paper_id}


@app.get("/api/lines")
def api_lines():
    from botdraw.lines import list_lines

    return list_lines()


@app.get("/api/lines/{line_id}/preview.svg")
def api_line_preview(line_id: str):
    from botdraw.lines import load_line, preview_svg

    try:
        stock = load_line(line_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Line not found") from None
    svg = preview_svg(stock)
    return Response(content=svg, media_type="image/svg+xml")


@app.post("/api/lines/save")
def api_line_save(body: LineSaveRequest):
    from botdraw.lines import LineStock, save_line

    stock = LineStock.model_validate(body.model_dump())
    save_line(stock)
    return stock.model_dump()


@app.delete("/api/lines/{line_id}")
def api_line_delete(line_id: str):
    from botdraw.lines import delete_line

    try:
        delete_line(line_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Line not found") from None
    return {"ok": True, "id": line_id}


@app.get("/api/portrait/line-types")
def api_portrait_line_types():
    from botdraw.portrait.ornament import LINE_TYPES

    return {"line_types": LINE_TYPES}


class PortraitIngestRequest(BaseModel):
    image_mode: str = "photo"
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED
    paper: PaperSize = PaperSize.A4
    crop: Optional[dict[str, Any]] = None
    auto_frame: bool = True
    force_reingest: bool = False
    ingest_id: Optional[str] = None
    reuse_ingest: bool = False
    include_preview_png: bool = True
    posterize_levels: Optional[int] = None
    filter_speckle: Optional[int] = None
    min_path_points: Optional[int] = None
    contrast: Optional[float] = None
    contour_simplify: Optional[int] = None
    hatch_size: Optional[int] = None
    linedraw_jitter: Optional[float] = None


def _portrait_ingest_response(pv, *, include_preview_png: bool = True) -> dict[str, Any]:
    from botdraw.portrait.preview import portrait_vector_preview_dict

    return portrait_vector_preview_dict(pv, include_preview_png=include_preview_png)


def _ingest_knobs_from_body(body: PortraitIngestRequest) -> dict[str, Any]:
    return {
        "posterize_levels": body.posterize_levels,
        "filter_speckle": body.filter_speckle,
        "min_path_points": body.min_path_points,
        "contrast": body.contrast,
        "contour_simplify": body.contour_simplify,
        "hatch_size": body.hatch_size,
        "linedraw_jitter": body.linedraw_jitter,
    }


@app.post("/api/portrait/ingest")
def api_portrait_ingest_json(body: PortraitIngestRequest):
    """Ingest only (no style/ornament) — synthetic face when no upload."""
    from botdraw.portrait import resolve_portrait_vector

    knobs = _ingest_knobs_from_body(body)
    if body.reuse_ingest and body.ingest_id and not body.force_reingest:
        pv, hit = resolve_portrait_vector(
            image_path=None,
            mode=body.image_mode,
            quality=body.quality.value,
            paper=body.paper.value,
            crop=body.crop,
            reuse_ingest=True,
            ingest_id=body.ingest_id,
            force_reingest=False,
            auto_frame=body.auto_frame if body.crop is None else False,
            **knobs,
        )
    else:
        pv, hit = resolve_portrait_vector(
            image_path=None,
            mode=body.image_mode,
            quality=body.quality.value,
            paper=body.paper.value,
            crop=body.crop,
            reuse_ingest=False,
            ingest_id=None,
            force_reingest=body.force_reingest,
            auto_frame=body.auto_frame if body.crop is None else False,
            **knobs,
        )
    data = _portrait_ingest_response(pv, include_preview_png=body.include_preview_png)
    data["cache_hit"] = hit
    return data


@app.post("/api/portrait/ingest/upload")
async def api_portrait_ingest_upload(
    image_mode: str = Form("photo"),
    quality: str = Form("booth-balanced"),
    paper: str = Form("A4"),
    crop: Optional[str] = Form(None),
    auto_frame: bool = Form(True),
    force_reingest: bool = Form(False),
    ingest_id: Optional[str] = Form(None),
    reuse_ingest: bool = Form(False),
    include_preview_png: bool = Form(True),
    posterize_levels: Optional[int] = Form(None),
    filter_speckle: Optional[int] = Form(None),
    min_path_points: Optional[int] = Form(None),
    contrast: Optional[float] = Form(None),
    contour_simplify: Optional[int] = Form(None),
    hatch_size: Optional[int] = Form(None),
    linedraw_jitter: Optional[float] = Form(None),
    file: UploadFile = File(...),
):
    from uuid import uuid4

    from botdraw.core.jobs import artifact_dir
    from botdraw.portrait import resolve_portrait_vector

    crop_obj = None
    if crop:
        try:
            crop_obj = json.loads(crop)
        except json.JSONDecodeError:
            crop_obj = None
    tmp = artifact_dir(uuid4().hex[:8]) / (file.filename or "upload.png")
    raw = await file.read()
    tmp.write_bytes(raw)
    pv, hit = resolve_portrait_vector(
        image_path=str(tmp),
        mode=image_mode or "photo",
        quality=quality,
        paper=paper,
        crop=crop_obj,
        reuse_ingest=reuse_ingest and not force_reingest,
        ingest_id=ingest_id,
        force_reingest=force_reingest,
        auto_frame=auto_frame if crop_obj is None else False,
        image_bytes=raw,
        posterize_levels=posterize_levels,
        filter_speckle=filter_speckle,
        min_path_points=min_path_points,
        contrast=contrast,
        contour_simplify=contour_simplify,
        hatch_size=hatch_size,
        linedraw_jitter=linedraw_jitter,
    )
    data = _portrait_ingest_response(pv, include_preview_png=include_preview_png)
    data["cache_hit"] = hit
    return data


@app.get("/api/portrait/ingest/{ingest_id}")
def api_portrait_ingest_get(ingest_id: str, include_preview_png: bool = True):
    from botdraw.portrait import load_portrait_vector

    pv = load_portrait_vector(ingest_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Ingest not found")
    data = _portrait_ingest_response(pv, include_preview_png=include_preview_png)
    data["cache_hit"] = True
    return data


@app.get("/api/portrait/ingest/{ingest_id}/svg")
def api_portrait_ingest_svg(ingest_id: str, paper_color_hex: str = "#f7f1e8"):
    from botdraw.portrait import load_portrait_vector
    from botdraw.portrait.preview import portrait_vector_raw_svg

    pv = load_portrait_vector(ingest_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Ingest not found")
    svg = portrait_vector_raw_svg(pv, paper_color_hex=paper_color_hex or "#f7f1e8")
    return Response(content=svg, media_type="image/svg+xml")


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
    extra = dict(body.params_extra or {})
    if body.paper_id:
        extra["paper_id"] = body.paper_id
    if body.paper_color_hex:
        extra["paper_color_hex"] = body.paper_color_hex
    if body.reuse_ingest:
        extra["reuse_ingest"] = True
    if body.ingest_id:
        extra["ingest_id"] = body.ingest_id
    if body.force_reingest:
        extra["force_reingest"] = True
    if body.crop:
        extra["crop"] = body.crop
    job, payload, layers = render_job(
        app=body.app,
        style_id=body.style_id,
        palette_id=body.palette_id,
        paper=body.paper,
        quality=body.quality,
        seed=body.seed,
        density=body.density,
        params_extra=extra,
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
    seed: int = Form(42),
    density: float = Form(1.0),
    pen_up_speed_mm_s: float = Form(100.0),
    pen_down_speed_mm_s: float = Form(25.0),
    image_mode: str = Form("photo"),
    params_extra: Optional[str] = Form(None),
    paper_id: Optional[str] = Form(None),
    paper_color_hex: Optional[str] = Form(None),
    reuse_ingest: bool = Form(False),
    ingest_id: Optional[str] = Form(None),
    force_reingest: bool = Form(False),
    crop: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    from botdraw.core.jobs import artifact_dir
    from uuid import uuid4

    extra: dict[str, Any] = {"image_mode": image_mode or "photo"}
    if params_extra:
        try:
            parsed = json.loads(params_extra)
            if isinstance(parsed, dict):
                extra.update(parsed)
        except json.JSONDecodeError:
            pass
    if paper_id:
        extra["paper_id"] = paper_id
    if paper_color_hex:
        extra["paper_color_hex"] = paper_color_hex
    if reuse_ingest:
        extra["reuse_ingest"] = True
    if ingest_id:
        extra["ingest_id"] = ingest_id
    if force_reingest:
        extra["force_reingest"] = True
    if crop:
        try:
            extra["crop"] = json.loads(crop)
        except json.JSONDecodeError:
            pass
    tmp = artifact_dir(uuid4().hex[:8]) / (file.filename or "upload.png")
    tmp.write_bytes(await file.read())
    job, payload, layers = render_job(
        app=app_name,
        style_id=style_id,
        palette_id=palette_id,
        paper=PaperSize(paper),
        quality=QualityPreset(quality),
        seed=seed,
        density=density,
        image_path=str(tmp),
        params_extra=extra,
        pen_up_speed_mm_s=pen_up_speed_mm_s,
        pen_down_speed_mm_s=pen_down_speed_mm_s,
    )
    return {"job": job.model_dump(), "emulator": payload, "layers": layers}


@app.get("/api/letters/fonts")
def api_letter_fonts():
    return {"fonts": list_fonts()}


@app.post("/api/letters/draft")
def api_letter_draft(body: LetterRequest):
    import time

    t0 = time.perf_counter()
    layer_models = body.layers or []
    primary_body = None
    if layer_models:
        primary_body = (layer_models[0].body or "").strip() or None
    if primary_body is None and body.body and body.body.strip():
        primary_body = body.body.strip()

    if primary_body:
        draft = {
            "source": "provided",
            "body": primary_body,
            "motif": None,
        }
    elif body.use_llm:
        try_local_ollama()
        draft = draft_wedding_letter(
            names=body.names,
            language=body.language,
            era=body.era,
            mood=body.mood,
            facts=body.facts,
            guest_quote=body.guest_quote,
        )
    else:
        unload()
        draft = draft_wedding_letter(
            names=body.names,
            language=body.language,
            era=body.era,
            mood=body.mood,
            facts=body.facts,
            guest_quote=body.guest_quote,
        )
    t_draft = time.perf_counter() - t0

    t1 = time.perf_counter()
    quote_for_layout = None if primary_body else body.guest_quote
    margins = body.margins or MarginsModel()
    m = Margins(left=margins.left, top=margins.top, right=margins.right, bottom=margins.bottom)

    if layer_models:
        specs: list[LetterLayerSpec] = []
        for i, lm in enumerate(layer_models):
            btxt = (lm.body or "").strip()
            if i == 0 and not btxt:
                btxt = draft["body"]
            lg = lm.line or LineGeomModel()
            sn = lm.snap or SnapModel()
            specs.append(
                LetterLayerSpec(
                    id=lm.id or f"layer-{i}",
                    name=lm.name or f"Layer {i + 1}",
                    body=btxt,
                    font_name=lm.font_name or body.font_name,
                    size_mm=lm.size_mm,
                    pen_id=lm.pen_id,
                    language=lm.language or body.language,
                    translate_from_en=lm.translate_from_en,
                    offset_x_mm=lm.offset_x_mm,
                    offset_y_mm=lm.offset_y_mm,
                    kind=lm.kind,
                    tracking=lm.tracking,
                    humanize=lm.humanize,
                    line_height=lm.line_height,
                    highlight_words=list(lm.highlight_words or []),
                    draw_mode=lm.draw_mode or "text",
                    leading_variation=lm.leading_variation,
                    line_angle_deg=lm.line_angle_deg,
                    line=LineGeom(
                        x0_mm=lg.x0_mm,
                        y0_mm=lg.y0_mm,
                        x1_mm=lg.x1_mm,
                        y1_mm=lg.y1_mm,
                        style=lg.style,
                        dash_mm=lg.dash_mm,
                        gap_mm=lg.gap_mm,
                        width_mm=lg.width_mm,
                    ),
                    placement=lm.placement or "freehand",
                    snap=SnapSpec(
                        target_layer_id=sn.target_layer_id,
                        span_index=sn.span_index,
                        role=sn.role or "underline",
                    ),
                )
            )
        layered = render_letter_layers(
            specs,
            palette_id=body.palette_id,
            paper=PaperSize(body.paper),
            orientation=body.orientation,
            margins=m,
            seed=body.seed,
            guest_quote=quote_for_layout,
        )
    else:
        if body.highlight:
            hl_words = body.highlight_words if body.highlight_words is not None else ["forever", "heart", "love"]
        else:
            hl_words = []
        layered = render_letter(
            draft["body"],
            palette_id=body.palette_id,
            paper=PaperSize(body.paper),
            language=body.language,
            guest_quote=quote_for_layout,
            highlight_words=hl_words,
            seed=body.seed,
            size_mm=body.size_mm,
            line_height=body.line_height,
            tracking=body.tracking,
            humanize=body.humanize,
            orientation=body.orientation,
            margins=m,
            font_name=body.font_name,
        )
    from botdraw.core.optimize import optimize_layered
    from botdraw.core.motion_plan import compile_motion_plan
    from botdraw.core.jobs import artifact_dir, save_job
    from botdraw.core.models import JobRecord, JobStatus
    from botdraw.core.svg import save_svg
    from botdraw.core.pipeline import layers_summary

    palette = load_palette(body.palette_id)
    if body.optimize:
        layered = optimize_layered(layered)
    else:
        layered.meta["optimizer"] = "skipped-reading-order"
    plan = compile_motion_plan(layered, palette)
    layers = layers_summary(layered, palette)
    t_vector = time.perf_counter() - t1
    translate_pending = bool(layered.meta.get("translate_pending"))
    settings = {
        "app": "lettersbot",
        "style_id": "letter",
        "letter_type": body.letter_type,
        "palette_id": body.palette_id,
        "seed": body.seed,
        "paper": body.paper,
        "orientation": body.orientation,
        "margins": margins.model_dump(),
        "language": body.language,
        "era": body.era,
        "mood": body.mood,
        "names": body.names,
        "guest_quote": body.guest_quote,
        "highlight": body.highlight,
        "size_mm": body.size_mm,
        "tracking": body.tracking,
        "humanize": body.humanize,
        "font_name": body.font_name,
        "use_llm": body.use_llm,
        "optimize": body.optimize,
        "draft_source": draft.get("source"),
        "missing_scripts": layered.meta.get("missing_scripts", []),
        "translate_pending": translate_pending,
        "translate_note": (
            "AI translation not processed yet — English source kept; enable when translator ships."
            if translate_pending
            else None
        ),
        "letter_layers": layered.meta.get("layers", []),
        "layer_spans": layered.meta.get("layer_spans", {}),
        "timing_s": {"draft": round(t_draft, 3), "vectorize": round(t_vector, 3)},
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
