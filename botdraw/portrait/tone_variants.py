"""Ensemble tone / focus recipes for multi-variant vectorization.

Blur-pyramid variants (sharp → soft) surface glasses vs silhouette better
than hue/sat knobs on faces. Numpy/Pillow only — no OpenCV.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class ToneRecipe:
    id: str
    contrast: float = 1.0
    shadow_lift: float = 0.0  # 0..1 — lift darks toward midtones
    highlight_compress: float = 0.0  # 0..1 — pull highlights down
    blur_radius: float = 0.0  # Gaussian blur radius (px); 0 = sharp
    hue_shift: float = 0.0  # kept for API compat; unused by default recipes
    saturation: float = 1.0


# Five focus-stack recipes: sharp detail → soft silhouette
ENSEMBLE_RECIPES: tuple[ToneRecipe, ...] = (
    ToneRecipe(id="sharp", contrast=1.12, blur_radius=0.0),
    ToneRecipe(id="sharp_punch", contrast=1.38, shadow_lift=0.16, blur_radius=0.0),
    ToneRecipe(id="medium_blur", contrast=1.14, blur_radius=1.6),
    ToneRecipe(id="soft_blur", contrast=1.10, blur_radius=3.2),
    ToneRecipe(id="silhouette_soft", contrast=1.22, blur_radius=5.0, highlight_compress=0.18),
)


def _contrast_mid(rgb: np.ndarray, amount: float) -> np.ndarray:
    if abs(float(amount) - 1.0) < 1e-3:
        return np.asarray(rgb, dtype=np.float32)
    mid = 128.0
    return np.clip((np.asarray(rgb, dtype=np.float32) - mid) * float(amount) + mid, 0, 255)


def _shadow_lift(rgb: np.ndarray, amount: float) -> np.ndarray:
    a = float(np.clip(amount, 0.0, 1.0))
    if a < 1e-4:
        return np.asarray(rgb, dtype=np.float32)
    x = np.asarray(rgb, dtype=np.float32) / 255.0
    lift = 1.0 - (1.0 - x) ** (1.0 + 1.6 * a)
    blended = x * (1.0 - a * 0.85) + lift * (a * 0.85)
    return np.clip(blended * 255.0, 0, 255).astype(np.float32)


def _highlight_compress(rgb: np.ndarray, amount: float) -> np.ndarray:
    a = float(np.clip(amount, 0.0, 1.0))
    if a < 1e-4:
        return np.asarray(rgb, dtype=np.float32)
    x = np.asarray(rgb, dtype=np.float32) / 255.0
    y = np.where(x > 0.55, 0.55 + (x - 0.55) * (1.0 - 0.65 * a), x)
    return np.clip(y * 255.0, 0, 255).astype(np.float32)


def _gaussian_blur_rgb(rgb: np.ndarray, radius: float) -> np.ndarray:
    r = float(radius)
    if r < 0.05:
        return np.asarray(rgb, dtype=np.float32)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    img = img.filter(ImageFilter.GaussianBlur(radius=r))
    return np.asarray(img, dtype=np.float32)


def apply_tone_recipe(rgb: np.ndarray, recipe: ToneRecipe) -> np.ndarray:
    """Apply one ToneRecipe to an RGB image → float32 RGB [0..255]."""
    out = np.asarray(rgb, dtype=np.float32)
    out = _gaussian_blur_rgb(out, recipe.blur_radius)
    out = _contrast_mid(out, recipe.contrast)
    out = _shadow_lift(out, recipe.shadow_lift)
    out = _highlight_compress(out, recipe.highlight_compress)
    return out
