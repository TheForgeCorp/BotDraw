"""Inkscape Trace Bitmap–inspired scan modes (algorithms only, no Potrace).

Named intermediates map onto linedraw / posterize knobs so the Ingest UI
can offer Brightness / Edges / Centerline / Color bands like Inkscape's
filter menu, while Hybrid C stays MIT/Apache.
"""

from __future__ import annotations

import base64
import io
from typing import Any

import numpy as np
from PIL import Image

from botdraw.portrait.linedraw_edges import (
    _spur_prune,
    _zhang_suen_thin,
    autocontrast_lum,
    edge_bitmap,
)

SCAN_MODES = ("auto", "brightness", "edges", "centerline", "color_bands")

SCAN_MODE_LABELS: dict[str, str] = {
    "auto": "Auto (Hybrid C)",
    "brightness": "Brightness",
    "edges": "Edges",
    "centerline": "Centerline",
    "color_bands": "Color bands",
}


def normalize_scan_mode(mode: str | None) -> str:
    m = (mode or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    if m in ("colour_bands", "color", "quantize"):
        return "color_bands"
    if m in ("canny", "edge"):
        return "edges"
    if m in ("skeleton", "centreline"):
        return "centerline"
    if m in ("threshold", "brightness_cutoff", "luma"):
        return "brightness"
    if m not in SCAN_MODES:
        return "auto"
    return m


def scan_mode_knobs(scan_mode: str) -> dict[str, Any]:
    """
    Knobs consumed by contours_from_lum / ingest.

    - prefer_silhouette: dual-axis long strokes
    - prefer_skeleton: Zhang–Suen centerline emphasis
    - soft_face_edges: interior face feature pass
    - region_boost: favor vtracer color bands
    """
    m = normalize_scan_mode(scan_mode)
    if m == "brightness":
        return {
            "prefer_silhouette": True,
            "prefer_skeleton": False,
            "soft_face_edges": False,
            "edge_low": 70.0,
            "edge_high": 140.0,
            "region_boost": False,
        }
    if m == "edges":
        return {
            "prefer_silhouette": False,
            "prefer_skeleton": True,
            "soft_face_edges": True,
            "edge_low": 36.0,
            "edge_high": 85.0,
            "region_boost": False,
        }
    if m == "centerline":
        return {
            "prefer_silhouette": False,
            "prefer_skeleton": True,
            "soft_face_edges": False,
            "edge_low": 48.0,
            "edge_high": 110.0,
            "region_boost": False,
        }
    if m == "color_bands":
        return {
            "prefer_silhouette": True,
            "prefer_skeleton": True,
            "soft_face_edges": True,
            "edge_low": 50.0,
            "edge_high": 115.0,
            "region_boost": True,
        }
    # auto
    return {
        "prefer_silhouette": True,
        "prefer_skeleton": True,
        "soft_face_edges": True,
        "edge_low": None,
        "edge_high": None,
        "region_boost": False,
    }


def build_scan_intermediate(
    lum: np.ndarray,
    rgb: np.ndarray | None,
    scan_mode: str,
    *,
    posterize_levels: int = 6,
) -> np.ndarray:
    """
    Build an 8-bit preview of the Inkscape-style intermediate bitmap.

    Returns HxW (L) or HxWx3 (RGB for color_bands) uint8 array.
    """
    m = normalize_scan_mode(scan_mode)
    u8 = autocontrast_lum(np.asarray(lum, dtype=np.float32), cutoff=6.0)
    if m == "brightness":
        # Lighter intermediate first (Inkscape advice) — threshold mid-high
        thr = 140
        return ((u8.astype(np.float32) < thr) * 255).astype(np.uint8)
    if m == "edges":
        mask = edge_bitmap(u8.astype(np.float32), low=36.0, high=85.0)
        return (mask.astype(np.uint8) * 255)
    if m == "centerline":
        mask = edge_bitmap(u8.astype(np.float32), low=48.0, high=110.0)
        # Downscale thin for speed on preview
        h, w = mask.shape
        sc = max(1, int(max(h, w) / 360))
        if sc > 1:
            small = np.asarray(
                Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
                    (max(8, w // sc), max(8, h // sc)), Image.Resampling.NEAREST
                ),
                dtype=np.uint8,
            ) > 127
        else:
            small = mask
        skel = _spur_prune(_zhang_suen_thin(small, max_iter=10), min_spur=4)
        if sc > 1:
            skel = np.asarray(
                Image.fromarray((skel.astype(np.uint8) * 255), mode="L").resize(
                    (w, h), Image.Resampling.NEAREST
                ),
                dtype=np.uint8,
            ) > 127
        return (skel.astype(np.uint8) * 255)
    if m == "color_bands":
        arr = np.asarray(rgb if rgb is not None else np.stack([u8, u8, u8], axis=-1), dtype=np.float32)
        n = max(2, min(16, int(posterize_levels) or 6))
        step = 255.0 / (n - 1)
        q = np.clip(np.round(arr / step) * step, 0, 255).astype(np.uint8)
        return q
    # auto: edge map overlay on dim luma
    mask = edge_bitmap(u8.astype(np.float32), low=50.0, high=110.0)
    base = (u8.astype(np.float32) * 0.45).astype(np.uint8)
    out = np.stack([base, base, base], axis=-1)
    out[mask] = (40, 200, 220)
    return out


def intermediate_to_png_b64(arr: np.ndarray, *, max_side: int = 480) -> str | None:
    try:
        a = np.asarray(arr)
        if a.ndim == 2:
            img = Image.fromarray(a.astype(np.uint8), mode="L")
        else:
            img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), mode="RGB")
        w, h = img.size
        scale = max_side / max(w, h)
        if scale < 1:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None
