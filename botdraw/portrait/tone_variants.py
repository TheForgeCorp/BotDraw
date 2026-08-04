"""Fixed RGB tone recipes for ensemble multi-variant vectorization.

Numpy/Pillow only — no OpenCV. Mild hue/sat shifts keep selfie likeness
while splitting channels that collapse under a single luminance pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ToneRecipe:
    id: str
    contrast: float = 1.0
    shadow_lift: float = 0.0  # 0..1 — lift darks toward midtones
    highlight_compress: float = 0.0  # 0..1 — pull highlights down
    hue_shift: float = 0.0  # degrees, mild (±~18)
    saturation: float = 1.0  # scale around 1.0


# Five fixed recipes: base + four complementary exposures
ENSEMBLE_RECIPES: tuple[ToneRecipe, ...] = (
    ToneRecipe(id="base", contrast=1.12),
    ToneRecipe(id="high_contrast_shadows", contrast=1.35, shadow_lift=0.22),
    ToneRecipe(id="soft_highlights", contrast=0.92, highlight_compress=0.28, shadow_lift=0.08),
    ToneRecipe(id="cool_desat", contrast=1.15, hue_shift=-14.0, saturation=0.72),
    ToneRecipe(id="warm_punch", contrast=1.18, hue_shift=12.0, saturation=1.28, shadow_lift=0.1),
)


def _rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized RGB[0..255] → H[0..360), S[0..1], V[0..1]."""
    x = np.clip(np.asarray(rgb, dtype=np.float32), 0, 255) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    v = maxc
    delta = maxc - minc
    s = np.where(maxc > 1e-6, delta / np.maximum(maxc, 1e-6), 0.0)

    h = np.zeros_like(maxc)
    mask = delta > 1e-6
    rc = np.where(mask, (maxc - r) / np.maximum(delta, 1e-6), 0.0)
    gc = np.where(mask, (maxc - g) / np.maximum(delta, 1e-6), 0.0)
    bc = np.where(mask, (maxc - b) / np.maximum(delta, 1e-6), 0.0)

    rmax = mask & (maxc == r)
    gmax = mask & (maxc == g) & ~rmax
    bmax = mask & ~rmax & ~gmax
    h = np.where(rmax, (bc - gc) * 60.0, h)
    h = np.where(gmax, (2.0 + rc - bc) * 60.0, h)
    h = np.where(bmax, (4.0 + gc - rc) * 60.0, h)
    h = np.mod(h, 360.0)
    return h, s.astype(np.float32), v.astype(np.float32)


def _hsv_to_rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    """H[0..360), S/V[0..1] → RGB float32 [0..255]."""
    h = np.mod(np.asarray(h, dtype=np.float32), 360.0)
    s = np.clip(np.asarray(s, dtype=np.float32), 0, 1)
    v = np.clip(np.asarray(v, dtype=np.float32), 0, 1)
    c = v * s
    x = c * (1.0 - np.abs(np.mod(h / 60.0, 2.0) - 1.0))
    m = v - c
    z = np.zeros_like(h)
    rgb = np.zeros(h.shape + (3,), dtype=np.float32)
    sext = (h // 60.0).astype(np.int32) % 6
    # 0: c,x,0  1: x,c,0  2: 0,c,x  3: 0,x,c  4: x,0,c  5: c,0,x
    for i, (rr, gg, bb) in enumerate(
        (
            (c, x, z),
            (x, c, z),
            (z, c, x),
            (z, x, c),
            (x, z, c),
            (c, z, x),
        )
    ):
        sel = sext == i
        if not np.any(sel):
            continue
        rgb[sel, 0] = rr[sel]
        rgb[sel, 1] = gg[sel]
        rgb[sel, 2] = bb[sel]
    rgb = (rgb + m[..., None]) * 255.0
    return np.clip(rgb, 0, 255).astype(np.float32)


def _contrast_mid(rgb: np.ndarray, amount: float) -> np.ndarray:
    if abs(float(amount) - 1.0) < 1e-3:
        return np.asarray(rgb, dtype=np.float32)
    mid = 128.0
    return np.clip((np.asarray(rgb, dtype=np.float32) - mid) * float(amount) + mid, 0, 255)


def _shadow_lift(rgb: np.ndarray, amount: float) -> np.ndarray:
    """Lift darks toward midtones without blowing highlights."""
    a = float(np.clip(amount, 0.0, 1.0))
    if a < 1e-4:
        return np.asarray(rgb, dtype=np.float32)
    x = np.asarray(rgb, dtype=np.float32) / 255.0
    # Power curve on V-like mean: lift lows
    lift = 1.0 - (1.0 - x) ** (1.0 + 1.6 * a)
    blended = x * (1.0 - a * 0.85) + lift * (a * 0.85)
    return np.clip(blended * 255.0, 0, 255).astype(np.float32)


def _highlight_compress(rgb: np.ndarray, amount: float) -> np.ndarray:
    a = float(np.clip(amount, 0.0, 1.0))
    if a < 1e-4:
        return np.asarray(rgb, dtype=np.float32)
    x = np.asarray(rgb, dtype=np.float32) / 255.0
    # Soft knee on bright values
    y = np.where(x > 0.55, 0.55 + (x - 0.55) * (1.0 - 0.65 * a), x)
    return np.clip(y * 255.0, 0, 255).astype(np.float32)


def apply_tone_recipe(rgb: np.ndarray, recipe: ToneRecipe) -> np.ndarray:
    """Apply one ToneRecipe to an RGB float/uint image → float32 RGB [0..255]."""
    out = np.asarray(rgb, dtype=np.float32)
    out = _contrast_mid(out, recipe.contrast)
    out = _shadow_lift(out, recipe.shadow_lift)
    out = _highlight_compress(out, recipe.highlight_compress)
    need_hsv = abs(recipe.hue_shift) > 0.05 or abs(recipe.saturation - 1.0) > 1e-3
    if need_hsv:
        h, s, v = _rgb_to_hsv(out)
        h = np.mod(h + float(recipe.hue_shift), 360.0)
        s = np.clip(s * float(recipe.saturation), 0.0, 1.0)
        out = _hsv_to_rgb(h, s, v)
    return out
