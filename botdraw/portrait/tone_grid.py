"""Explicit midtone intensity grid → coded pen recipes (no OpenCV).

Shade regions without hard edges get a per-cell intensity code that
selects hatch / cross / scribble density. Edges stay on the structure path.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from botdraw.portrait.linedraw_edges import (
    _make_perlin_table,
    _midtone_hatch_mask,
    _perlin_noise,
    autocontrast_lum,
    face_roi_mask,
)


# Code → recipe (plan table)
# 0 skip/highlight | 1 light hatch | 2 mid+cross | 3 dense | 4 scribble shadow | 5 edge-only


def build_tone_grid(
    lum: np.ndarray,
    ink_target: np.ndarray,
    *,
    cell_px: int,
    edge_map: np.ndarray | None = None,
    page_w_mm: float,
    page_h_mm: float,
    max_code: int = 4,
) -> dict[str, Any]:
    """
    Build coarse tone_grid (0..1) and tone_codes (uint8).

    Returns dict with tone_grid, tone_codes, tone_cell_px, tone_cell_mm, tone_origin_mm.
    """
    sc = max(4, int(cell_px))
    h0, w0 = lum.shape
    w_s = max(4, w0 // sc)
    h_s = max(4, int(round(h0 * (w_s / w0))))

    lum_s = np.asarray(
        Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.LANCZOS
        ),
        dtype=np.float32,
    )
    ink_full = np.asarray(ink_target, dtype=np.float32)
    # Soft shade: max of ink with lightly blurred pyramid (fills cheek valleys)
    ink_blur = np.asarray(
        Image.fromarray(np.clip(ink_full * 255.0, 0, 255).astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(1.0, sc * 0.35))
        ),
        dtype=np.float32,
    ) / 255.0
    ink_soft = np.maximum(ink_full, ink_blur * 0.85)
    ink_s = np.asarray(
        Image.fromarray(np.clip(ink_soft * 255.0, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.LANCZOS
        ),
        dtype=np.float32,
    ) / 255.0

    u8 = autocontrast_lum(lum_s, cutoff=6.0)
    allow = _midtone_hatch_mask(u8.astype(np.float32))
    face = face_roi_mask(lum)
    face_s = np.asarray(
        Image.fromarray((face.astype(np.uint8) * 255), mode="L").resize(
            (w_s, h_s), Image.Resampling.NEAREST
        ),
        dtype=np.uint8,
    ) > 127

    # Soft shade: also allow low-structure face midtones (cheeks)
    face_mid = face_s & (u8.astype(np.float32) >= 70.0) & (u8.astype(np.float32) <= 210.0)
    allow = allow | (face_mid & (ink_s >= 0.08))

    # Edge proximity → suppress muddy fill (code 5)
    edge_near = np.zeros((h_s, w_s), dtype=bool)
    if edge_map is not None:
        em = np.asarray(edge_map, dtype=np.float32)
        if em.shape != (h0, w0):
            em = np.asarray(
                Image.fromarray(np.clip(em, 0, 255).astype(np.uint8), mode="L").resize(
                    (w0, h0), Image.Resampling.NEAREST
                ),
                dtype=np.float32,
            )
        em_s = np.asarray(
            Image.fromarray((em > 20).astype(np.uint8) * 255, mode="L").resize(
                (w_s, h_s), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127
        from numpy.lib.stride_tricks import sliding_window_view

        pad = np.pad(em_s.astype(np.uint8), 1, mode="constant")
        edge_near = sliding_window_view(pad, (3, 3)).max(axis=(2, 3)).astype(bool)

    tone_grid = np.zeros((h_s, w_s), dtype=np.float32)
    tone_codes = np.zeros((h_s, w_s), dtype=np.uint8)
    max_code = int(np.clip(max_code, 1, 5))

    for y in range(h_s):
        for x in range(w_s):
            if not allow[y, x]:
                continue
            ink = float(ink_s[y, x])
            # Outside face: require more ink to avoid wall grids
            if not face_s[y, x] and ink < 0.22:
                continue
            if edge_near[y, x] and ink < 0.55:
                # Structure cell — leave to edges
                tone_grid[y, x] = ink
                tone_codes[y, x] = 5
                continue
            tone_grid[y, x] = ink
            if ink < 0.12:
                code = 0
            elif ink < 0.28:
                code = 1
            elif ink < 0.42:
                code = 2
            elif ink < 0.58:
                code = 3
            elif ink < 0.78:
                code = 4
            else:
                code = 5  # near-black: edges only
            tone_codes[y, x] = min(code, max_code) if code < 5 else 5
            if max_code < 4 and tone_codes[y, x] == 4:
                tone_codes[y, x] = 3

    cell_mm_x = page_w_mm / max(w0, 1) * sc
    cell_mm_y = page_h_mm / max(h0, 1) * sc
    return {
        "tone_grid": tone_grid,
        "tone_codes": tone_codes,
        "tone_cell_px": float(sc),
        "tone_cell_mm": float((cell_mm_x + cell_mm_y) * 0.5),
        "tone_origin_mm": (0.0, 0.0),
        "grid_shape": (h_s, w_s),
        "img_shape": (h0, w0),
    }


def strokes_from_tone_grid(
    tone_codes: np.ndarray,
    *,
    cell_px: float,
    img_w: int,
    img_h: int,
    page_w: float,
    page_h: float,
    style: str = "hatch",
    jitter: float = 0.04,
    seed: int = 1,
    max_paths: int = 4000,
) -> list[list[tuple[float, float]]]:
    """
    Turn tone_codes into px polylines, then map to mm.

    style: "hatch" | "scribble"
    """
    from botdraw.portrait.linedraw_edges import polylines_to_mm

    hs = float(cell_px)
    h_s, w_s = tone_codes.shape
    table = _make_perlin_table(seed)
    lg1: list[list[tuple[float, float]]] = []
    lg2: list[list[tuple[float, float]]] = []
    scribbles: list[list[tuple[float, float]]] = []

    for y0 in range(h_s):
        for x0 in range(w_s):
            code = int(tone_codes[y0, x0])
            if code <= 0 or code >= 5:
                continue
            x = x0 * hs
            y = y0 * hs + (0.12 * hs if (x0 % 2) else 0.0)
            if style == "scribble" and code >= 3:
                ink = 0.35 + 0.15 * (code - 3)
                n_seg = 2 if code == 3 else 3
                amp = hs * (0.14 + 0.32 * ink)
                period = max(3, int(6 - 2 * ink))
                y_base = y0 * hs + hs * 0.5
                for s in range(n_seg):
                    pts: list[tuple[float, float]] = []
                    y_off = (s - (n_seg - 1) / 2.0) * hs * 0.2
                    for k in range(period + 1):
                        t = k / period
                        px = x0 * hs + t * hs
                        wave = amp * math.sin(t * math.pi * (1.5 + ink))
                        jx = hs * jitter * (_perlin_noise(table, x0 * 0.2, y0 * 0.2 + s, k * 0.3) - 0.5)
                        jy = hs * jitter * (_perlin_noise(table, x0 * 0.2, y0 * 0.2 + s, k * 0.3 + 3) - 0.5)
                        pts.append((px + jx, y_base + y_off + wave + jy))
                    if len(pts) >= 2:
                        scribbles.append(pts)
                continue

            # Hatch recipes by code
            if code == 1:
                lg1.append([(x, y + hs * 0.4), (x + hs, y + hs * 0.4)])
            elif code == 2:
                lg1.append([(x, y + hs * 0.35), (x + hs, y + hs * 0.35)])
                if (x0 + y0) % 2 == 0:
                    lg2.append([(x + hs, y), (x, y + hs)])
            else:  # 3 or hatch-fallback for 4
                lg1.append([(x, y + hs * 0.25), (x + hs, y + hs * 0.25)])
                lg1.append([(x, y + hs * 0.65), (x + hs, y + hs * 0.65)])
                lg2.append([(x + hs, y), (x, y + hs)])
                if style == "hatch" and code == 4:
                    lg2.append([(x, y), (x + hs, y + hs)])

    def join_collinear(lines: list[list[tuple[float, float]]], thresh: float = 0.85) -> list[list[tuple[float, float]]]:
        lines = [list(l) for l in lines]
        changed = True
        while changed:
            changed = False
            for i in range(len(lines)):
                if not lines[i]:
                    continue
                for j in range(len(lines)):
                    if i == j or not lines[j]:
                        continue
                    ax, ay = lines[i][-1]
                    bx, by = lines[j][0]
                    if abs(ax - bx) < thresh and abs(ay - by) < thresh:
                        lines[i] = lines[i] + lines[j][1:]
                        lines[j] = []
                        changed = True
            lines = [l for l in lines if len(l) > 0]
        return lines

    if style == "scribble":
        # Mix light hatch (1–2) + scribbles (3–4)
        lines = join_collinear(lg1) + join_collinear(lg2) + scribbles
    else:
        lines = join_collinear(lg1) + join_collinear(lg2)

    amount = float(hs) * float(jitter) * 0.2
    out_px: list[list[tuple[float, float]]] = []
    for i, line in enumerate(lines):
        if len(line) < 2:
            continue
        if math.hypot(line[-1][0] - line[0][0], line[-1][1] - line[0][1]) < hs * 0.45:
            continue
        pts = []
        for j, (px, py) in enumerate(line):
            jx = amount * (_perlin_noise(table, i * 0.5, j * 0.1, 1.0) - 0.5) * 2.0
            jy = amount * (_perlin_noise(table, i * 0.5, j * 0.1, 2.0) - 0.5) * 2.0
            pts.append((px + jx, py + jy))
        out_px.append(pts)
        if len(out_px) >= max_paths:
            break

    return polylines_to_mm(
        out_px[:max_paths],
        img_w=img_w,
        img_h=img_h,
        page_w=page_w,
        page_h=page_h,
    )


def tone_codes_heatmap_rgb(tone_codes: np.ndarray) -> np.ndarray:
    """False-color preview: 0=paper, 1–4=yellow→red, 5=teal (edge-only)."""
    h, w = tone_codes.shape
    out = np.full((h, w, 3), 247, dtype=np.uint8)  # paper-ish
    palette = {
        1: (250, 220, 120),
        2: (240, 170, 70),
        3: (220, 100, 50),
        4: (160, 40, 60),
        5: (40, 160, 180),
    }
    for code, rgb in palette.items():
        out[tone_codes == code] = rgb
    return out
