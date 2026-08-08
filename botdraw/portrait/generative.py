"""
Generative portrait ink stage (studio-first).

Produces a monochrome ink raster (0..1, dark = ink) that ingest vectorizes
into plotter strokes. This is the drawing path for ``line_source=generative``;
vision review remains a knob controller and does not generate strokes.

Providers (``BOTDRAW_GENERATIVE_PROVIDER``):
- ``manual`` — load PNG/JPEG from ``BOTDRAW_GENERATIVE_INK`` (subscription/chat)
- ``openai`` — Images API edit/generate from the photo (``OPENAI_API_KEY``)
- ``gemini`` — Gemini image generation from the photo

Fail closed: missing key/package/file/API errors return None so ingest can
fall back to neural then classic. CI never calls live APIs.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

ProviderName = Literal["manual", "openai", "gemini"]
PROVIDERS: tuple[ProviderName, ...] = ("manual", "openai", "gemini")

# Ingest-time likeness gate: generative ink vs photo darkness correlation.
GENERATIVE_TONE_CORR_MIN = 0.05

INK_PROMPT = (
    "Convert this head-and-shoulders portrait photograph into a clean "
    "pen-plotter line drawing: black ink on pure white background, "
    "preserve likeness of eyes nose mouth and silhouette, crisp contour "
    "lines, minimal interior texture, no photoreal shading blobs, no text, "
    "no watermark, no color."
)

INK_PROMPT_STRICT = (
    INK_PROMPT
    + " Prefer fewer strokes; emphasize facial feature edges and outer silhouette only."
)


def default_provider() -> ProviderName:
    raw = (os.environ.get("BOTDRAW_GENERATIVE_PROVIDER") or "").strip().lower()
    if raw in PROVIDERS:
        return raw  # type: ignore[return-value]
    # Prefer an API provider when a key is already configured; else manual.
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "manual"


def provider_status() -> dict[str, dict[str, Any]]:
    oai_pkg = False
    gem_pkg = False
    try:
        import openai  # noqa: F401

        oai_pkg = True
    except ImportError:
        pass
    try:
        import google.genai  # noqa: F401

        gem_pkg = True
    except ImportError:
        try:
            import google.generativeai  # noqa: F401

            gem_pkg = True
        except ImportError:
            pass

    ink_path = (os.environ.get("BOTDRAW_GENERATIVE_INK") or "").strip()
    return {
        "manual": {
            "key": bool(ink_path),
            "package": True,
            "ready": bool(ink_path) and Path(ink_path).expanduser().is_file(),
            "ink_path": ink_path or None,
        },
        "openai": {
            "key": bool(os.environ.get("OPENAI_API_KEY")),
            "package": oai_pkg,
            "ready": bool(os.environ.get("OPENAI_API_KEY")) and oai_pkg,
            "model": os.environ.get("BOTDRAW_GENERATIVE_OPENAI_MODEL")
            or os.environ.get("BOTDRAW_OPENAI_IMAGE_MODEL")
            or "gpt-image-1",
        },
        "gemini": {
            "key": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
            "package": gem_pkg,
            "ready": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
            and gem_pkg,
            "model": os.environ.get("BOTDRAW_GENERATIVE_GEMINI_MODEL")
            or "gemini-2.0-flash-preview-image-generation",
        },
    }


def generative_available(provider: str | None = None) -> bool:
    name = (provider or default_provider()).strip().lower()
    info = provider_status().get(name)
    return bool(info and info.get("ready"))


def generative_unavailable_reason(provider: str | None = None) -> str | None:
    if generative_available(provider):
        return None
    name = (provider or default_provider()).strip().lower()
    if name not in PROVIDERS:
        return f"generative provider unknown: {name!r} (use manual|openai|gemini)"
    info = provider_status().get(name) or {}
    if name == "manual":
        return (
            "generative manual provider unavailable: set BOTDRAW_GENERATIVE_INK "
            "to a PNG/JPEG line-drawing path."
        )
    if not info.get("package"):
        return (
            f"generative {name} unavailable: install vision extras "
            '(`pip install -e ".[vision]"`).'
        )
    if not info.get("key"):
        key = "OPENAI_API_KEY" if name == "openai" else "GEMINI_API_KEY or GOOGLE_API_KEY"
        return f"generative {name} unavailable: missing {key}."
    return f"generative {name} unavailable."


def _rgb_to_pil(rgb: np.ndarray) -> Image.Image:
    arr = np.clip(np.asarray(rgb), 0, 255).astype(np.uint8)
    if arr.ndim == 2:
        return Image.fromarray(arr, mode="L").convert("RGB")
    return Image.fromarray(arr[..., :3], mode="RGB")


def raster_to_ink(img: Image.Image, *, height: int, width: int) -> np.ndarray:
    """Resize any image to HxW and convert to ink density (dark = 1)."""
    gray = img.convert("L").resize((width, height), Image.Resampling.LANCZOS)
    lum = np.asarray(gray, dtype=np.float32) / 255.0
    return np.clip(1.0 - lum, 0.0, 1.0).astype(np.float32)


def ink_to_png_bytes(ink: np.ndarray) -> bytes:
    """Encode ink (0..1 dark) as a white-paper PNG for artifacts."""
    paper = np.clip((1.0 - np.asarray(ink, dtype=np.float32)) * 255.0, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(paper, mode="L").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def ink_tone_corr(gen_ink: np.ndarray, photo_ink: np.ndarray) -> float:
    """Pearson correlation between generative ink and photo darkness."""
    a = np.asarray(gen_ink, dtype=np.float32).reshape(-1)
    b = np.asarray(photo_ink, dtype=np.float32).reshape(-1)
    if a.size != b.size or a.size == 0:
        return 0.0
    if float(a.std()) < 1e-6 or float(b.std()) < 1e-6:
        return 0.0
    corr = float(np.corrcoef(a, b)[0, 1])
    return corr if np.isfinite(corr) else 0.0


def _load_manual_ink(
    *,
    height: int,
    width: int,
    ink_path: str | Path | None = None,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    path_s = str(ink_path or os.environ.get("BOTDRAW_GENERATIVE_INK") or "").strip()
    if not path_s:
        return None
    path = Path(path_s).expanduser()
    if not path.is_file():
        return None
    try:
        img = Image.open(path)
        img.load()
    except Exception:
        return None
    ink = raster_to_ink(img, height=height, width=width)
    meta = {"provider": "manual", "ink_path": str(path.resolve()), "prompt_variant": "file"}
    return ink, meta


def _openai_ink(rgb: np.ndarray, *, prompt: str, seed: int) -> tuple[np.ndarray, dict[str, Any]] | None:
    try:
        from openai import OpenAI
    except ImportError:
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    h, w = int(rgb.shape[0]), int(rgb.shape[1])
    model = (
        os.environ.get("BOTDRAW_GENERATIVE_OPENAI_MODEL")
        or os.environ.get("BOTDRAW_OPENAI_IMAGE_MODEL")
        or "gpt-image-1"
    )
    src = _rgb_to_pil(rgb)
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    buf.seek(0)
    try:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        # images.edit accepts the source photo + prompt (image-to-image).
        result = client.images.edit(
            model=model,
            image=("portrait.png", buf.getvalue(), "image/png"),
            prompt=prompt,
            n=1,
        )
        data0 = (result.data or [None])[0]
        if data0 is None:
            return None
        b64 = getattr(data0, "b64_json", None)
        if not b64 and getattr(data0, "url", None):
            import httpx

            resp = httpx.get(data0.url, timeout=120.0)
            resp.raise_for_status()
            out_img = Image.open(io.BytesIO(resp.content))
        elif b64:
            out_img = Image.open(io.BytesIO(base64.b64decode(b64)))
        else:
            return None
        out_img.load()
    except Exception:
        return None
    ink = raster_to_ink(out_img, height=h, width=w)
    meta = {"provider": "openai", "model": model, "seed": int(seed), "prompt_variant": prompt[:48]}
    return ink, meta


def _gemini_ink(rgb: np.ndarray, *, prompt: str, seed: int) -> tuple[np.ndarray, dict[str, Any]] | None:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return None
    h, w = int(rgb.shape[0]), int(rgb.shape[1])
    model = (
        os.environ.get("BOTDRAW_GENERATIVE_GEMINI_MODEL")
        or "gemini-2.0-flash-preview-image-generation"
    )
    src = _rgb_to_pil(rgb)
    src_bytes = io.BytesIO()
    src.save(src_bytes, format="PNG")
    png = src_bytes.getvalue()
    try:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            )
            parts = [
                types.Part.from_bytes(data=png, mime_type="image/png"),
                types.Part.from_text(text=prompt),
            ]
            resp = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            out_img = None
            for cand in getattr(resp, "candidates", None) or []:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        out_img = Image.open(io.BytesIO(inline.data))
                        break
                if out_img is not None:
                    break
            if out_img is None:
                return None
            out_img.load()
        except Exception:
            # Legacy google.generativeai path
            import google.generativeai as genai_old

            genai_old.configure(
                api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            )
            model_obj = genai_old.GenerativeModel(model)
            resp = model_obj.generate_content([prompt, {"mime_type": "image/png", "data": png}])
            out_img = None
            for cand in getattr(resp, "candidates", None) or []:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        out_img = Image.open(io.BytesIO(inline.data))
                        break
                if out_img is not None:
                    break
            if out_img is None:
                return None
            out_img.load()
    except Exception:
        return None
    ink = raster_to_ink(out_img, height=h, width=w)
    meta = {"provider": "gemini", "model": model, "seed": int(seed), "prompt_variant": prompt[:48]}
    return ink, meta


def _call_provider(
    rgb: np.ndarray,
    *,
    provider: ProviderName,
    prompt: str,
    seed: int,
    ink_path: str | Path | None = None,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    h, w = int(rgb.shape[0]), int(rgb.shape[1])
    if provider == "manual":
        return _load_manual_ink(height=h, width=w, ink_path=ink_path)
    if provider == "openai":
        return _openai_ink(rgb, prompt=prompt, seed=seed)
    if provider == "gemini":
        return _gemini_ink(rgb, prompt=prompt, seed=seed)
    return None


def generate_portrait_ink(
    rgb: np.ndarray,
    *,
    provider: str | None = None,
    seed: int = 0,
    ink_path: str | Path | None = None,
    photo_ink_target: np.ndarray | None = None,
    tone_corr_min: float = GENERATIVE_TONE_CORR_MIN,
    allow_retry: bool = True,
) -> dict[str, Any] | None:
    """
    Return ``{ink, meta}`` or None on failure.

    When ``photo_ink_target`` is provided, score tone correlation and — if
    below ``tone_corr_min`` — retry once with a stricter prompt / next seed,
    keeping the better of the two attempts.
    """
    name = (provider or default_provider()).strip().lower()
    if name not in PROVIDERS:
        return None
    prov: ProviderName = name  # type: ignore[assignment]

    attempts: list[tuple[np.ndarray, dict[str, Any], float]] = []
    prompts = [INK_PROMPT]
    if allow_retry:
        prompts.append(INK_PROMPT_STRICT)

    for i, prompt in enumerate(prompts):
        got = _call_provider(
            rgb,
            provider=prov,
            prompt=prompt,
            seed=int(seed) + i,
            ink_path=ink_path,
        )
        if got is None:
            if i == 0:
                return None
            break
        ink, meta = got
        corr = (
            ink_tone_corr(ink, photo_ink_target)
            if photo_ink_target is not None
            else 0.0
        )
        meta = {
            **meta,
            "tone_corr": corr,
            "attempt": i,
            "seed": int(seed) + i,
        }
        attempts.append((ink, meta, corr))
        if photo_ink_target is None or corr >= float(tone_corr_min) or not allow_retry:
            break

    if not attempts:
        return None

    # Keep the best correlation (manual file is usually attempt 0 only).
    ink, meta, corr = max(attempts, key=lambda t: t[2])
    png = ink_to_png_bytes(ink)
    fidelity = {
        "tone_corr": corr,
        "tone_corr_min": float(tone_corr_min),
        "passed": bool(photo_ink_target is None or corr >= float(tone_corr_min)),
        "attempts": len(attempts),
        "kept_attempt": int(meta.get("attempt") or 0),
    }
    return {
        "ink": ink,
        "meta": {
            **meta,
            "fidelity": fidelity,
            "ink_png_b64": base64.b64encode(png).decode("ascii"),
        },
    }
