"""PortraitBot: preprocess, ingest, pen assign, restyle, ornament."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from botdraw.portrait.cache import load_portrait_vector, resolve_portrait_vector, save_portrait_vector
from botdraw.portrait.frame import auto_frame_rgb, normalize_crop
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.models import CropRect, PortraitVector
from botdraw.portrait.ornament import LINE_TYPES, StrokeOrnamentParams, decorate_layered
from botdraw.portrait.pens import apply_pen_overrides, assign_pens
from botdraw.portrait.preview import portrait_vector_preview_dict, portrait_vector_raw_svg
from botdraw.portrait.restyle import render_from_vector
from botdraw.portrait.tone_variants import ENSEMBLE_RECIPES, ToneRecipe, apply_tone_recipe


def preprocess_portrait_image(
    path: str | Path,
    *,
    mode: str = "photo",
    max_side: int = 640,
) -> np.ndarray:
    """
    Load and lightly preprocess an upload for plotter styles.

    Modes (vectorizer.io-inspired):
    - photo: full color / continuous tone (default)
    - sketch: grayscale contrast boost (many midtones)
    - lineart: edge emphasis for sparse line engines
    - drawing: hard black/white threshold
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

    m = (mode or "photo").lower()
    if m == "sketch":
        g = ImageOps.autocontrast(ImageOps.grayscale(img))
        img = Image.merge("RGB", (g, g, g))
    elif m == "lineart":
        g = ImageOps.grayscale(img)
        edges = g.filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.invert(ImageOps.autocontrast(edges))
        img = Image.merge("RGB", (edges, edges, edges))
    elif m == "drawing":
        g = ImageOps.grayscale(img)
        bw = g.point(lambda x: 255 if x > 160 else 0)
        img = Image.merge("RGB", (bw, bw, bw))

    return np.asarray(img, dtype=np.float32)


__all__ = [
    "CropRect",
    "ENSEMBLE_RECIPES",
    "LINE_TYPES",
    "PortraitVector",
    "StrokeOrnamentParams",
    "ToneRecipe",
    "apply_pen_overrides",
    "apply_tone_recipe",
    "assign_pens",
    "auto_frame_rgb",
    "decorate_layered",
    "ingest_portrait",
    "load_portrait_vector",
    "normalize_crop",
    "portrait_vector_preview_dict",
    "portrait_vector_raw_svg",
    "preprocess_portrait_image",
    "render_from_vector",
    "resolve_portrait_vector",
    "save_portrait_vector",
]
