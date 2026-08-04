"""PortraitBot image preprocessing helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps


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
        # Keep soft paper background with dark strokes
        img = Image.merge("RGB", (edges, edges, edges))
    elif m == "drawing":
        g = ImageOps.grayscale(img)
        bw = g.point(lambda x: 255 if x > 160 else 0)
        img = Image.merge("RGB", (bw, bw, bw))
    # photo: leave RGB

    return np.asarray(img, dtype=np.float32)
