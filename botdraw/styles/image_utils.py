"""Shared image helpers for style engines."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load_image_array(path: str | Path, max_side: int = 640) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return np.asarray(img, dtype=np.float32)


def luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def map_to_page(
    ix: float,
    iy: float,
    *,
    img_w: int,
    img_h: int,
    page_w: float,
    page_h: float,
    margin: float = 10.0,
) -> tuple[float, float]:
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    scale = min(usable_w / img_w, usable_h / img_h)
    x = margin + (usable_w - img_w * scale) / 2 + ix * scale
    y = margin + (usable_h - img_h * scale) / 2 + iy * scale
    return x, y


def synthetic_portrait(size: int = 320) -> np.ndarray:
    """Generate a simple face-like test image when no upload is provided."""
    yy, xx = np.mgrid[0:size, 0:size]
    cx, cy = size / 2, size / 2
    face = ((xx - cx) ** 2 / (size * 0.28) ** 2 + (yy - cy * 0.95) ** 2 / (size * 0.34) ** 2) < 1
    eye_l = (xx - cx + size * 0.1) ** 2 + (yy - cy * 0.85) ** 2 < (size * 0.03) ** 2
    eye_r = (xx - cx - size * 0.1) ** 2 + (yy - cy * 0.85) ** 2 < (size * 0.03) ** 2
    mouth = (
        (np.abs(yy - cy * 1.15) < size * 0.015)
        & (np.abs(xx - cx) < size * 0.12)
    )
    rgb = np.ones((size, size, 3), dtype=np.float32) * 240
    rgb[face] = (220, 180, 150)
    rgb[eye_l | eye_r] = (30, 30, 40)
    rgb[mouth] = (140, 60, 70)
    return rgb
