"""
Vision review for portrait ingest/output (Anthropic / OpenAI / Gemini).

The vision model is a reviewer + controller, not a stroke engine:
- ``review_photo`` → PortraitScene JSON → ingest knobs
- ``critique_render`` → PortraitCritique JSON → one re-restyle / re-ingest

Modes (``ai_review``):
- ``off`` — no vision
- ``live`` — scene knobs only (booth-safe; never critique / AI re-ingest)
- ``studio`` — scene + one critique; structure fixes may re-ingest once

Bool ``true`` resolves by quality: booth-* → live, studio-hq → studio.

Providers (env ``BOTDRAW_VISION_PROVIDER`` or per-call):
- ``anthropic`` — ANTHROPIC_API_KEY
- ``openai`` — OPENAI_API_KEY
- ``gemini`` — GEMINI_API_KEY or GOOGLE_API_KEY
- ``manual`` — load JSON from BOTDRAW_VISION_SCENE_JSON /
  BOTDRAW_VISION_CRITIQUE_JSON (subscription/chat while API keys pending)

Fail closed: missing key/package/API errors return None and callers keep
the current neural/classic path. Action/fix keys are a closed dictionary
mapped onto real knobs — never free-form code execution.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

ProviderName = Literal["anthropic", "openai", "gemini", "manual"]
PROVIDERS: tuple[ProviderName, ...] = ("anthropic", "openai", "gemini", "manual")

AiReviewMode = Literal["off", "live", "studio"]
AI_REVIEW_MODES: tuple[AiReviewMode, ...] = ("off", "live", "studio")


# ---------------------------------------------------------------------------
# Closed action / fix dictionaries (never execute free-form model output)
# ---------------------------------------------------------------------------

ALLOWED_FIXES = frozenset(
    {
        "suppress_background",
        "keep_more_edges",
        "equalize_structure",
        "fix_crop",
        "boost_pet_shade",
        "boost_face_shade",
        "reduce_background_edges",
        "prefer_scribble",
        "prefer_linework",
    }
)

ALLOWED_ACTION_KEYS = frozenset(
    {
        "force_reingest",
        "line_source",
        "hatch_budget_mul",
        "style_id",
        "max_tone_code",
        "suppress_background",
        "density_mul",
        "scan_mode",
        "contour_simplify",
    }
)

# Dev / studio feedback loop — pass history visualizes quality return
VISION_MAX_TURNS = 10
VISION_MAX_REINGESTS = 5

SCENE_SYSTEM = """You review a portrait photograph for a pen-plotter pipeline.
Return ONLY valid JSON matching this schema (no markdown):
{
  "orientation_deg": 0 | 90 | 180 | 270,
  "subjects": [{"kind": "person"|"pet"|"other", "importance": 0..1}],
  "clutter": ["wire_crate"|"blinds"|"busy_bg"|"text"|string],
  "lighting": "normal"|"backlit_window"|"dim"|"harsh",
  "crop_hint": {"x":0..1,"y":0..1,"w":0..1,"h":0..1} | null,
  "ingest": {
    "line_source": "neural"|"classic"|"auto",
    "suppress_background": bool,
    "protect_subjects": ["person","pet"],
    "max_tone_code": 3|4
  },
  "summary": "one short sentence"
}
orientation_deg is the clockwise rotation needed to make subjects upright.
Flag pets and geometric clutter (blinds, crates). Prefer neural lines +
background suppress for multi-subject or cluttered scenes."""

STRUCTURE_CRITIQUE_SYSTEM = """You critique pen-plotter STRUCTURE linework (ingest Raw SVG /
edge polylines) against the source photo. Focus on missing edges, open silhouettes,
parallel-band gaps, noise/travel, and crop. Return ONLY valid JSON:
{
  "overall": 0..1,
  "issues": [
    {"code": string, "severity": 0..1, "region": string|null,
     "fix": "suppress_background"|"keep_more_edges"|"equalize_structure"|
            "fix_crop"|"boost_pet_shade"|"boost_face_shade"|
            "reduce_background_edges"|"prefer_scribble"|"prefer_linework"}
  ],
  "actions": {
    "force_reingest": bool,
    "line_source": "neural"|"classic"|"auto"|null,
    "hatch_budget_mul": number|null,
    "style_id": string|null,
    "max_tone_code": 3|4|null,
    "suppress_background": bool|null,
    "density_mul": number|null,
    "scan_mode": "auto"|"edges"|"brightness"|"centerline"|"color_bands"|null,
    "contour_simplify": 1|2|3|null
  },
  "summary": "one short sentence"
}
Prefer classic line_source for structure rescue. Smallest change that closes gaps."""

CRITIQUE_SYSTEM = """You critique a pen-plotter portrait preview against the source photo.
Return ONLY valid JSON matching this schema (no markdown):
{
  "overall": 0..1,
  "issues": [
    {"code": string, "severity": 0..1, "region": string|null,
     "fix": "suppress_background"|"keep_more_edges"|"equalize_structure"|
            "fix_crop"|"boost_pet_shade"|"boost_face_shade"|
            "reduce_background_edges"|"prefer_scribble"|"prefer_linework"}
  ],
  "actions": {
    "force_reingest": bool,
    "line_source": "neural"|"classic"|"auto"|null,
    "hatch_budget_mul": number|null,
    "style_id": string|null,
    "max_tone_code": 3|4|null,
    "suppress_background": bool|null,
    "density_mul": number|null,
    "scan_mode": "auto"|"edges"|"brightness"|"centerline"|"color_bands"|null,
    "contour_simplify": 1|2|3|null
  },
  "summary": "one short sentence"
}
Only use the listed fix/action keys. Prefer the smallest change that helps likeness."""


class SubjectInfo(BaseModel):
    kind: Literal["person", "pet", "other"] = "person"
    importance: float = Field(default=1.0, ge=0.0, le=1.0)


class CropHint(BaseModel):
    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    w: float = Field(default=1.0, ge=0.05, le=1.0)
    h: float = Field(default=1.0, ge=0.05, le=1.0)


class IngestHints(BaseModel):
    line_source: Literal["neural", "classic", "auto"] = "neural"
    suppress_background: bool = True
    protect_subjects: list[str] = Field(default_factory=lambda: ["person"])
    max_tone_code: int = Field(default=4, ge=3, le=4)


class PortraitScene(BaseModel):
    orientation_deg: Literal[0, 90, 180, 270] = 0
    subjects: list[SubjectInfo] = Field(default_factory=list)
    clutter: list[str] = Field(default_factory=list)
    lighting: str = "normal"
    crop_hint: CropHint | None = None
    ingest: IngestHints = Field(default_factory=IngestHints)
    summary: str = ""


class CritiqueIssue(BaseModel):
    code: str
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    region: str | None = None
    fix: str


class CritiqueActions(BaseModel):
    force_reingest: bool = False
    line_source: Literal["neural", "classic", "auto"] | None = None
    hatch_budget_mul: float | None = Field(default=None, ge=0.5, le=3.0)
    style_id: str | None = None
    max_tone_code: int | None = Field(default=None, ge=3, le=4)
    suppress_background: bool | None = None
    density_mul: float | None = Field(default=None, ge=0.5, le=2.5)
    scan_mode: Literal["auto", "edges", "brightness", "centerline", "color_bands"] | None = None
    contour_simplify: int | None = Field(default=None, ge=1, le=3)


class PortraitCritique(BaseModel):
    overall: float = Field(default=0.5, ge=0.0, le=1.0)
    issues: list[CritiqueIssue] = Field(default_factory=list)
    actions: CritiqueActions = Field(default_factory=CritiqueActions)
    summary: str = ""


def default_provider() -> ProviderName:
    raw = (os.environ.get("BOTDRAW_VISION_PROVIDER") or "anthropic").strip().lower()
    if raw in PROVIDERS:
        return raw  # type: ignore[return-value]
    return "anthropic"


def resolve_ai_review_mode(value: Any, *, quality: str | None = None) -> AiReviewMode:
    """
    Normalize ai_review into off | live | studio.

    Bool/\"true\" resolves by quality: studio-hq → studio, else live (booth-safe).
    """
    if value is None or value is False:
        return "off"
    if value is True:
        q = (quality or "").strip().lower().replace("_", "-")
        return "studio" if q == "studio-hq" else "live"
    raw = str(value).strip().lower()
    if raw in ("", "0", "false", "no", "off"):
        return "off"
    if raw in ("live", "scene"):
        return "live"
    if raw in ("studio", "full", "critique"):
        return "studio"
    if raw in ("1", "true", "yes", "on"):
        q = (quality or "").strip().lower().replace("_", "-")
        return "studio" if q == "studio-hq" else "live"
    return "off"


def ai_review_wants_scene(mode: AiReviewMode | str) -> bool:
    return mode in ("live", "studio")


def ai_review_wants_critique(mode: AiReviewMode | str) -> bool:
    return mode == "studio"


def provider_status() -> dict[str, dict[str, Any]]:
    """Which vision providers can run in this environment."""
    out: dict[str, dict[str, Any]] = {}
    # anthropic
    try:
        import anthropic  # noqa: F401

        anth_pkg = True
    except ImportError:
        anth_pkg = False
    out["anthropic"] = {
        "key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "package": anth_pkg,
        "ready": bool(os.environ.get("ANTHROPIC_API_KEY")) and anth_pkg,
        "model": os.environ.get("BOTDRAW_CLAUDE_MODEL", "claude-sonnet-4-20250514"),
    }
    # openai
    try:
        import openai  # noqa: F401

        oai_pkg = True
    except ImportError:
        oai_pkg = False
    out["openai"] = {
        "key": bool(os.environ.get("OPENAI_API_KEY")),
        "package": oai_pkg,
        "ready": bool(os.environ.get("OPENAI_API_KEY")) and oai_pkg,
        "model": os.environ.get("BOTDRAW_OPENAI_MODEL", "gpt-4.1"),
    }
    # gemini
    try:
        from google import genai  # noqa: F401

        gem_pkg = True
    except ImportError:
        try:
            import google.generativeai  # noqa: F401

            gem_pkg = True
        except ImportError:
            gem_pkg = False
    gem_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    out["gemini"] = {
        "key": gem_key,
        "package": gem_pkg,
        "ready": gem_key and gem_pkg,
        "model": os.environ.get("BOTDRAW_GEMINI_MODEL", "gemini-2.0-flash"),
    }
    # manual / subscription JSON (multi-turn dir or single files)
    scene_path = os.environ.get("BOTDRAW_VISION_SCENE_JSON") or ""
    critique_path = os.environ.get("BOTDRAW_VISION_CRITIQUE_JSON") or ""
    turns_dir = os.environ.get("BOTDRAW_VISION_TURNS_DIR") or ""
    turns_ready = False
    if turns_dir and Path(turns_dir).is_dir():
        turns_ready = (Path(turns_dir) / "turn01_scene.json").exists() or (
            Path(turns_dir) / "turn01.json"
        ).exists()
    out["manual"] = {
        "key": True,
        "package": True,
        "ready": bool((scene_path and Path(scene_path).exists()) or turns_ready),
        "model": "subscription-json",
        "scene_json": scene_path or None,
        "critique_json": critique_path or None,
        "turns_dir": turns_dir or None,
        "critique_ready": bool(
            (critique_path and Path(critique_path).exists())
            or turns_ready
        ),
        "max_turns": VISION_MAX_TURNS,
    }
    return out


def vision_available(provider: ProviderName | None = None) -> bool:
    p = provider or default_provider()
    return bool(provider_status().get(p, {}).get("ready"))


def claude_available() -> bool:
    """Backward-compatible alias: Anthropic API ready."""
    return vision_available("anthropic")


def _rgb_to_jpeg_b64(rgb: np.ndarray, *, max_side: int = 1280) -> str:
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _rgb_to_jpeg_bytes(rgb: np.ndarray, *, max_side: int = 1280) -> bytes:
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Recover JSON object if model wrapped it in prose
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
    return json.loads(text)


def _call_anthropic_vision(
    *,
    system: str,
    prompt: str,
    image_b64: str,
    media_type: str = "image/jpeg",
    model: str | None = None,
    images: list[tuple[str, str]] | None = None,
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    content: list[dict[str, Any]] = []
    for b64, mt in images or [(image_b64, media_type)]:
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mt, "data": b64},
            }
        )
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(
        model=model or os.environ.get("BOTDRAW_CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    parts = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _call_openai_vision(
    *,
    system: str,
    prompt: str,
    image_b64: str,
    media_type: str = "image/jpeg",
    model: str | None = None,
    images: list[tuple[str, str]] | None = None,
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for b64, mt in images or [(image_b64, media_type)]:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mt};base64,{b64}"},
            }
        )
    resp = client.chat.completions.create(
        model=model or os.environ.get("BOTDRAW_OPENAI_MODEL", "gpt-4.1"),
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    )
    return resp.choices[0].message.content or ""


def _call_gemini_vision(
    *,
    system: str,
    prompt: str,
    image_b64: str,
    media_type: str = "image/jpeg",
    model: str | None = None,
    images: list[tuple[str, str]] | None = None,
) -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY missing")
    model_name = model or os.environ.get("BOTDRAW_GEMINI_MODEL", "gemini-2.0-flash")
    # Prefer new google-genai SDK; fall back to google-generativeai
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        parts: list[Any] = [types.Part.from_text(text=f"{system}\n\n{prompt}")]
        for b64, mt in images or [(image_b64, media_type)]:
            parts.append(
                types.Part.from_bytes(data=base64.standard_b64decode(b64), mime_type=mt)
            )
        resp = client.models.generate_content(model=model_name, contents=parts)
        return getattr(resp, "text", None) or str(resp)
    except ImportError:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model_obj = genai.GenerativeModel(model_name, system_instruction=system)
        parts = [prompt]
        for b64, mt in images or [(image_b64, media_type)]:
            parts.append({"mime_type": mt, "data": base64.standard_b64decode(b64)})
        resp = model_obj.generate_content(parts)
        return resp.text or ""


def _call_vision(
    *,
    system: str,
    prompt: str,
    image_b64: str,
    media_type: str = "image/jpeg",
    model: str | None = None,
    provider: ProviderName | None = None,
    images: list[tuple[str, str]] | None = None,
) -> str:
    """Dispatch to the configured vision provider."""
    p = provider or default_provider()
    if p == "anthropic":
        return _call_anthropic_vision(
            system=system,
            prompt=prompt,
            image_b64=image_b64,
            media_type=media_type,
            model=model,
            images=images,
        )
    if p == "openai":
        return _call_openai_vision(
            system=system,
            prompt=prompt,
            image_b64=image_b64,
            media_type=media_type,
            model=model,
            images=images,
        )
    if p == "gemini":
        return _call_gemini_vision(
            system=system,
            prompt=prompt,
            image_b64=image_b64,
            media_type=media_type,
            model=model,
            images=images,
        )
    if p == "manual":
        path = os.environ.get("BOTDRAW_VISION_SCENE_JSON")
        if not path or not Path(path).exists():
            raise RuntimeError("BOTDRAW_VISION_SCENE_JSON not set or missing")
        return Path(path).read_text(encoding="utf-8")
    raise RuntimeError(f"Unknown vision provider: {p}")


# Backward-compatible name used by tests / stubs
_call_claude_vision = _call_vision


# Normalize chat-authored clutter labels onto the closed ingest set
_CLUTTER_ALIASES = {
    "window_blinds": "blinds",
    "blind": "blinds",
    "blinds": "blinds",
    "wire_crate": "wire_crate",
    "crate": "wire_crate",
    "busy_bg": "busy_bg",
    "busy_background": "busy_bg",
    "text": "text",
}


def load_scene_json(path: str | Path) -> PortraitScene:
    """Load a chat/subscription-authored scene JSON from disk."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # Allow richer manual schemas; keep only PortraitScene fields
    if isinstance(data.get("clutter"), list):
        clutter: list[str] = []
        for c in data["clutter"]:
            raw = str(c.get("id") or c.get("name") or c) if isinstance(c, dict) else str(c)
            clutter.append(_CLUTTER_ALIASES.get(raw.lower().strip(), raw))
        data = {**data, "clutter": clutter}
    if isinstance(data.get("subjects"), list):
        subjects = []
        for s in data["subjects"]:
            if isinstance(s, dict):
                subjects.append(
                    {
                        "kind": s.get("kind") or "person",
                        "importance": float(s.get("importance", 1.0)),
                    }
                )
        data = {**data, "subjects": subjects}
    # Drop unknown top-level keys before validate (framing, restyle_hints, …)
    keep = {
        "orientation_deg",
        "subjects",
        "clutter",
        "lighting",
        "crop_hint",
        "ingest",
        "summary",
    }
    data = {k: v for k, v in data.items() if k in keep}
    return PortraitScene.model_validate(data)


def load_critique_json(path: str | Path) -> PortraitCritique:
    """Load a chat/subscription-authored critique JSON from disk."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    keep = {"overall", "issues", "actions", "summary"}
    data = {k: v for k, v in data.items() if k in keep}
    critique = PortraitCritique.model_validate(data)
    kept = [i for i in critique.issues if i.fix in ALLOWED_FIXES]
    critique.issues = kept[:12]
    acts = critique.actions.model_dump()
    acts = {k: v for k, v in acts.items() if k in ALLOWED_ACTION_KEYS}
    critique.actions = CritiqueActions.model_validate(acts)
    critique.actions = _enrich_actions_from_fixes(critique)
    return critique


def vision_turns_dir() -> Path | None:
    raw = (os.environ.get("BOTDRAW_VISION_TURNS_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def resolve_manual_turn_path(turn: int) -> Path | None:
    """
    Resolve subscription JSON for a 1-indexed turn.

    Prefer BOTDRAW_VISION_TURNS_DIR/turnNN*.json, then legacy single-file env vars
    (turn 1 → SCENE, turn 2 → CRITIQUE, turn 3+ → FEEDBACK or CRITIQUE).
    """
    turn = int(turn)
    tdir = vision_turns_dir()
    if tdir is not None:
        candidates = [
            tdir / f"turn{turn:02d}_scene.json",
            tdir / f"turn{turn:02d}_critique.json",
            tdir / f"turn{turn:02d}.json",
        ]
        for c in candidates:
            if c.exists():
                return c
    if turn <= 1:
        path = os.environ.get("BOTDRAW_VISION_SCENE_JSON") or ""
        return Path(path) if path and Path(path).exists() else None
    if turn == 2:
        path = os.environ.get("BOTDRAW_VISION_CRITIQUE_JSON") or ""
        return Path(path) if path and Path(path).exists() else None
    path = (
        os.environ.get("BOTDRAW_VISION_FEEDBACK_JSON")
        or os.environ.get("BOTDRAW_VISION_CRITIQUE_JSON")
        or ""
    )
    return Path(path) if path and Path(path).exists() else None


def load_manual_turn(turn: int) -> PortraitScene | PortraitCritique | None:
    """Load scene (turn 1) or critique (turn 2+) from manual/subscription JSON."""
    path = resolve_manual_turn_path(turn)
    if path is None:
        return None
    try:
        if turn <= 1 or "scene" in path.name:
            return load_scene_json(path)
        return load_critique_json(path)
    except (ValidationError, json.JSONDecodeError, Exception):
        return None


def review_photo(
    rgb: np.ndarray,
    *,
    client_call=_call_vision,
    provider: ProviderName | None = None,
) -> PortraitScene | None:
    """Pre-ingest scene review. Returns None when unavailable or on error."""
    p = provider or default_provider()
    if client_call is _call_vision and not vision_available(p):
        return None
    try:
        if p == "manual" and client_call is _call_vision:
            path = os.environ.get("BOTDRAW_VISION_SCENE_JSON")
            if not path:
                tpath = resolve_manual_turn_path(1)
                path = str(tpath) if tpath else None
            if not path:
                return None
            scene = load_scene_json(path)
        else:
            raw = client_call(
                system=SCENE_SYSTEM,
                prompt="Analyze this portrait photo for pen-plotter ingest. JSON only.",
                image_b64=_rgb_to_jpeg_b64(rgb),
                provider=p,
            )
            data = _extract_json(raw)
            scene = PortraitScene.model_validate(data)
        scene.clutter = [str(c) for c in scene.clutter][:12]
        return scene
    except (ValidationError, json.JSONDecodeError, Exception):
        return None


def critique_render(
    source_rgb: np.ndarray,
    preview_png: bytes,
    *,
    style_id: str,
    client_call=_call_vision,
    provider: ProviderName | None = None,
    turn: int | None = None,
    structure: bool = False,
) -> PortraitCritique | None:
    """Post-render / post-structure critique. Returns None when unavailable or on error."""
    p = provider or default_provider()
    system = STRUCTURE_CRITIQUE_SYSTEM if structure else CRITIQUE_SYSTEM
    if p == "manual":
        path = None
        if turn is not None:
            path = resolve_manual_turn_path(int(turn))
        if path is None:
            env = os.environ.get("BOTDRAW_VISION_CRITIQUE_JSON") or ""
            path = Path(env) if env and Path(env).exists() else None
        if path is None:
            return None
        try:
            # Scene files are not critiques
            if "scene" in path.name:
                return None
            return load_critique_json(path)
        except (ValidationError, json.JSONDecodeError, Exception):
            return None
    if client_call is _call_vision and not vision_available(p):
        return None
    try:
        src_b64 = _rgb_to_jpeg_b64(source_rgb)
        prev_b64 = base64.standard_b64encode(preview_png).decode("ascii")
        raw = _critique_two_images(
            source_b64=src_b64,
            preview_b64=prev_b64,
            style_id=style_id,
            client_call=client_call,
            provider=p,
            system=system,
        )
        data = _extract_json(raw)
        critique = PortraitCritique.model_validate(data)
        kept = []
        for issue in critique.issues:
            if issue.fix in ALLOWED_FIXES:
                kept.append(issue)
        critique.issues = kept[:12]
        acts = critique.actions.model_dump()
        acts = {k: v for k, v in acts.items() if k in ALLOWED_ACTION_KEYS}
        critique.actions = CritiqueActions.model_validate(acts)
        critique.actions = _enrich_actions_from_fixes(critique)
        return critique
    except (ValidationError, json.JSONDecodeError, Exception):
        return None


def _critique_two_images(
    *,
    source_b64: str,
    preview_b64: str,
    style_id: str,
    client_call,
    provider: ProviderName | None = None,
    system: str | None = None,
) -> str:
    sys = system or CRITIQUE_SYSTEM
    prompt = (
        f"Image 1 = source photo. Image 2 = plotter preview "
        f"(style={style_id}). Critique likeness. JSON only."
    )
    if client_call is not _call_vision:
        # Tests inject a single-image stub; pass preview only with style context.
        return client_call(
            system=sys,
            prompt=f"Style={style_id}. Critique this plotter preview vs a source portrait. JSON only.",
            image_b64=preview_b64,
            media_type="image/png",
        )
    return client_call(
        system=sys,
        prompt=prompt,
        image_b64=source_b64,
        media_type="image/jpeg",
        provider=provider,
        images=[(source_b64, "image/jpeg"), (preview_b64, "image/png")],
    )


def compare_providers_scene(
    rgb: np.ndarray,
    *,
    providers: list[ProviderName] | None = None,
) -> dict[str, Any]:
    """
    Run scene review on every ready provider (plus any explicitly listed).
    Returns {provider: scene_dict | {"error": ...}}.
    """
    want = providers or list(PROVIDERS)
    status = provider_status()
    results: dict[str, Any] = {}
    for p in want:
        if p == "manual" and not status["manual"]["ready"]:
            results[p] = {"error": "set BOTDRAW_VISION_SCENE_JSON to a scene file"}
            continue
        if p != "manual" and not status.get(p, {}).get("ready"):
            results[p] = {"error": "not ready (key or package missing)", "status": status.get(p)}
            continue
        scene = review_photo(rgb, provider=p)
        if scene is None:
            results[p] = {"error": "review failed or invalid JSON"}
        else:
            results[p] = scene.model_dump()
    return results


def _enrich_actions_from_fixes(critique: PortraitCritique) -> CritiqueActions:
    acts = critique.actions
    fixes = {i.fix for i in critique.issues if i.severity >= 0.55}
    if "suppress_background" in fixes or "reduce_background_edges" in fixes:
        if acts.suppress_background is None:
            acts.suppress_background = True
    if "boost_pet_shade" in fixes or "boost_face_shade" in fixes:
        if acts.hatch_budget_mul is None:
            acts.hatch_budget_mul = 1.3
        if acts.density_mul is None:
            acts.density_mul = 1.15
    if "prefer_scribble" in fixes and not acts.style_id:
        acts.style_id = "portrait_scribble_tone"
    if "prefer_linework" in fixes and not acts.style_id:
        acts.style_id = "portrait_linework"
    if ("keep_more_edges" in fixes or "equalize_structure" in fixes) and acts.force_reingest is False:
        # Structure rescue: re-ingest once; keep classic unless JSON set a source
        acts.force_reingest = True
        if acts.line_source is None:
            acts.line_source = "classic"
    if "fix_crop" in fixes and acts.force_reingest is False:
        acts.force_reingest = True
    return acts


def apply_orientation(rgb: np.ndarray, orientation_deg: int) -> np.ndarray:
    """Rotate image so subjects are upright. orientation_deg = CW correction."""
    deg = int(orientation_deg) % 360
    if deg == 0:
        return rgb
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    # PIL rotate is CCW; CW correction = CCW of (360-deg)
    out = img.rotate(360 - deg, expand=True)
    return np.asarray(out, dtype=np.float32)


def scene_to_ingest_knobs(scene: PortraitScene) -> dict[str, Any]:
    """Map PortraitScene onto real ingest/resolve knobs (closed dictionary)."""
    knobs: dict[str, Any] = {
        "line_source": scene.ingest.line_source,
        "suppress_background": bool(scene.ingest.suppress_background),
        "max_tone_code": int(scene.ingest.max_tone_code),
        "protect_subjects": list(scene.ingest.protect_subjects),
        "orientation_deg": int(scene.orientation_deg),
        "ai_scene": scene.model_dump(),
    }
    # Stronger suppress when geometric clutter present
    clutter = {c.lower() for c in scene.clutter}
    if clutter & {"wire_crate", "blinds", "busy_bg"}:
        knobs["suppress_background"] = True
        if knobs["line_source"] == "auto":
            knobs["line_source"] = "neural"
    # Pet protection → expand subject matte later in ingest
    kinds = {s.kind for s in scene.subjects}
    if "pet" in kinds and "pet" not in knobs["protect_subjects"]:
        knobs["protect_subjects"].append("pet")
    if scene.crop_hint is not None:
        ch = scene.crop_hint
        # Clamp crop inside unit square
        x = float(np.clip(ch.x, 0, 0.95))
        y = float(np.clip(ch.y, 0, 0.95))
        w = float(np.clip(ch.w, 0.05, 1.0 - x))
        h = float(np.clip(ch.h, 0.05, 1.0 - y))
        knobs["crop"] = {"x": x, "y": y, "w": w, "h": h, "source": "ai_scene"}
        knobs["auto_frame"] = False
    return knobs


def critique_to_render_knobs(critique: PortraitCritique) -> dict[str, Any]:
    """Map PortraitCritique actions onto render/ingest knobs."""
    a = critique.actions
    out: dict[str, Any] = {
        "ai_critique": critique.model_dump(),
    }
    if a.force_reingest:
        out["force_reingest"] = True
    if a.line_source:
        out["line_source"] = a.line_source
    if a.style_id:
        out["style_id"] = a.style_id
    if a.max_tone_code is not None:
        out["max_tone_code"] = a.max_tone_code
    if a.suppress_background is not None:
        out["suppress_background"] = a.suppress_background
    if a.hatch_budget_mul is not None:
        out["hatch_budget_mul"] = float(a.hatch_budget_mul)
    if a.density_mul is not None:
        out["density_mul"] = float(a.density_mul)
    if a.scan_mode:
        out["scan_mode"] = a.scan_mode
    if a.contour_simplify is not None:
        out["contour_simplify"] = int(a.contour_simplify)
    return out


def maybe_review_and_merge_knobs(
    rgb: np.ndarray,
    knobs: dict[str, Any],
    *,
    enabled: bool,
    client_call=_call_claude_vision,
    mode: AiReviewMode | None = None,
    quality: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    If enabled, run scene review, rotate the image, merge knobs.
    Always returns (possibly rotated rgb, knobs). Fail closed = unchanged.
    Preserves resolved ai_review mode (live|studio) on the merged knobs.
    """
    if not enabled:
        return rgb, knobs
    if mode is not None:
        resolved = mode
    else:
        resolved = resolve_ai_review_mode(
            knobs.get("ai_review"),
            quality=quality or knobs.get("quality"),
        )
        # enabled=True with no mode/flag → scene pass (live)
        if resolved == "off":
            resolved = "live"
    if not ai_review_wants_scene(resolved):
        return rgb, knobs
    scene = review_photo(rgb, client_call=client_call)
    if scene is None:
        knobs = {
            **knobs,
            "ai_review": resolved,
            "ai_review_status": "scene_unavailable",
        }
        return rgb, knobs
    scene_knobs = scene_to_ingest_knobs(scene)
    merged = {
        **knobs,
        **scene_knobs,
        "ai_review": resolved,
        "ai_review_status": "scene",
    }
    # Explicit user line_source / crop wins over scene if already set to neural/classic
    if knobs.get("line_source") in ("neural", "classic"):
        merged["line_source"] = knobs["line_source"]
    if knobs.get("crop") is not None and knobs.get("crop_locked"):
        merged["crop"] = knobs["crop"]
        merged["auto_frame"] = knobs.get("auto_frame", False)
    rgb2 = apply_orientation(rgb, int(merged.get("orientation_deg") or 0))
    return rgb2, merged
