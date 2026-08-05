"""Subject framing: auto heuristic crop + manual crop."""

from __future__ import annotations

import numpy as np
from PIL import Image

from botdraw.portrait.models import CropRect


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def normalize_crop(crop: CropRect | dict | None, *, fallback: CropRect | None = None) -> CropRect:
    if crop is None:
        return fallback or CropRect()
    if isinstance(crop, CropRect):
        c = crop
    else:
        c = CropRect.model_validate(crop)
    w = max(0.05, min(1.0, c.w))
    h = max(0.05, min(1.0, c.h))
    x = _clamp01(c.x)
    y = _clamp01(c.y)
    if x + w > 1.0:
        x = max(0.0, 1.0 - w)
    if y + h > 1.0:
        y = max(0.0, 1.0 - h)
    return CropRect(x=x, y=y, w=w, h=h, source=c.source or "manual")


def auto_frame_rgb(rgb: np.ndarray, *, pad: float = 0.1) -> CropRect:
    """
    Heuristic subject box: largest contrast/dark mass, center-weighted.
    No ML face detector — booth-safe and fast.
    """
    h, w = rgb.shape[:2]
    if h < 8 or w < 8:
        return CropRect(source="auto")
    # Downscale for speed
    step = max(1, max(h, w) // 96)
    small = rgb[::step, ::step].astype(np.float32)
    lum = 0.299 * small[..., 0] + 0.587 * small[..., 1] + 0.114 * small[..., 2]
    # Contrast vs local mean
    ink = 1.0 - lum / 255.0
    # Center weight
    yy, xx = np.mgrid[0 : ink.shape[0], 0 : ink.shape[1]]
    cy, cx = ink.shape[0] / 2, ink.shape[1] / 2
    dist = np.sqrt(((yy - cy) / max(cy, 1)) ** 2 + ((xx - cx) / max(cx, 1)) ** 2)
    weight = ink * (1.0 - 0.35 * np.clip(dist, 0, 1))
    thr = max(0.12, float(np.percentile(weight, 70)))
    mask = weight >= thr
    if not np.any(mask):
        # Fall back to center square
        side = 0.7
        return CropRect(x=(1 - side) / 2, y=(1 - side) / 2, w=side, h=side, source="auto")
    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    # Map back to full-res normalized
    scale_y = step / h
    scale_x = step / w
    ny0 = y0 * scale_y
    nx0 = x0 * scale_x
    ny1 = (y1 + 1) * scale_y
    nx1 = (x1 + 1) * scale_x
    bw = max(0.2, nx1 - nx0)
    bh = max(0.2, ny1 - ny0)
    # Pad
    nx0 = max(0.0, nx0 - bw * pad)
    ny0 = max(0.0, ny0 - bh * pad)
    nx1 = min(1.0, nx1 + bw * pad)
    ny1 = min(1.0, ny1 + bh * pad)
    return normalize_crop(CropRect(x=nx0, y=ny0, w=nx1 - nx0, h=ny1 - ny0, source="auto"))


def apply_crop_pil(img: Image.Image, crop: CropRect) -> Image.Image:
    c = normalize_crop(crop)
    w, h = img.size
    x0 = int(round(c.x * w))
    y0 = int(round(c.y * h))
    x1 = int(round((c.x + c.w) * w))
    y1 = int(round((c.y + c.h) * h))
    x0 = max(0, min(w - 1, x0))
    y0 = max(0, min(h - 1, y0))
    x1 = max(x0 + 1, min(w, x1))
    y1 = max(y0 + 1, min(h, y1))
    return img.crop((x0, y0, x1, y1))


def apply_crop_array(rgb: np.ndarray, crop: CropRect) -> np.ndarray:
    c = normalize_crop(crop)
    h, w = rgb.shape[:2]
    x0 = int(round(c.x * w))
    y0 = int(round(c.y * h))
    x1 = int(round((c.x + c.w) * w))
    y1 = int(round((c.y + c.h) * h))
    x0 = max(0, min(w - 1, x0))
    y0 = max(0, min(h - 1, y0))
    x1 = max(x0 + 1, min(w, x1))
    y1 = max(y0 + 1, min(h, y1))
    return rgb[y0:y1, x0:x1].copy()
