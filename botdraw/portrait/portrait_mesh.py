"""Shared portrait mesh IR: per-cell features + inter-cell interface walks.

Fine grid (~5–8px) carries ink / tone codes / edge fraction. Shade and edge
continuity come from walking H/V interfaces — not isolated cell stamps.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

from botdraw.portrait.linedraw_edges import (
    _make_perlin_table,
    _midtone_hatch_mask,
    _perlin_noise,
    autocontrast_lum,
    face_roi_mask,
    polylines_to_mm,
)


def default_mesh_cell_px(quality: str) -> int:
    q = (quality or "").lower()
    if q == "booth-fast":
        return 8
    if q == "studio-hq":
        return 5
    return 6  # booth-balanced


def build_portrait_mesh(
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
    Build mesh arrays + interface adjacency.

    Returns dict compatible with tone_grid fields plus mesh_edge / mesh_face /
    link_h / link_v (bool arrays for shade joins).
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

    # Gradient at mesh res (for optional hatch direction / edge interface)
    gy, gx = np.gradient(lum_s.astype(np.float32))
    gmag = np.hypot(gx, gy) + 1e-6
    grad_x = (gx / gmag).astype(np.float32)
    grad_y = (gy / gmag).astype(np.float32)

    u8 = autocontrast_lum(lum_s, cutoff=6.0)
    allow = _midtone_hatch_mask(u8.astype(np.float32))
    face = face_roi_mask(lum)
    face_s = np.asarray(
        Image.fromarray((face.astype(np.uint8) * 255), mode="L").resize(
            (w_s, h_s), Image.Resampling.NEAREST
        ),
        dtype=np.uint8,
    ) > 127

    face_mid = (
        face_s
        & (lum_s >= 55.0)
        & (lum_s <= 230.0)
        & (ink_s >= 0.08)
        & (ink_s <= 0.70)
    )
    allow = allow | face_mid

    mesh_edge = np.zeros((h_s, w_s), dtype=np.float32)
    if edge_map is not None:
        em = np.asarray(edge_map, dtype=np.float32)
        if em.shape != (h0, w0):
            em = np.asarray(
                Image.fromarray(np.clip(em, 0, 255).astype(np.uint8), mode="L").resize(
                    (w0, h0), Image.Resampling.NEAREST
                ),
                dtype=np.float32,
            )
        em_bin = (em > 40).astype(np.float32)
        mesh_edge = np.asarray(
            Image.fromarray((em_bin * 255).astype(np.uint8), mode="L").resize(
                (w_s, h_s), Image.Resampling.BOX
            ),
            dtype=np.float32,
        ) / 255.0

    edge_strong = mesh_edge >= 0.28
    tone_grid = np.zeros((h_s, w_s), dtype=np.float32)
    tone_codes = np.zeros((h_s, w_s), dtype=np.uint8)
    max_code = int(np.clip(max_code, 1, 5))

    for y in range(h_s):
        for x in range(w_s):
            if not allow[y, x]:
                continue
            ink = float(ink_s[y, x])
            # Outside face: stricter skip (walls)
            if not face_s[y, x] and ink < 0.28:
                continue
            # Narrow structure cells only (glasses/hairline) — avoid cheek halo
            if edge_strong[y, x] and ink >= 0.40 and mesh_edge[y, x] >= 0.42:
                tone_grid[y, x] = ink
                tone_codes[y, x] = 5
                continue
            tone_grid[y, x] = ink
            if face_s[y, x]:
                if ink < 0.14:
                    code = 0
                elif ink < 0.28:
                    code = 1
                elif ink < 0.40:
                    code = 2
                elif ink < 0.55:
                    code = 3
                elif ink < 0.72:
                    code = 4
                else:
                    code = 4 if max_code >= 4 else 3
            else:
                if ink < 0.18:
                    code = 0
                elif ink < 0.30:
                    code = 1
                elif ink < 0.45:
                    code = 2
                elif ink < 0.58:
                    code = 3
                elif ink < 0.72:
                    code = 4
                else:
                    code = 5
            tone_codes[y, x] = min(code, max_code) if code < 5 else 5
            if max_code < 4 and tone_codes[y, x] == 4:
                tone_codes[y, x] = 3

    # Kill tiny outside-face shade islands (1–2 cells)
    shade_mask = (tone_codes >= 1) & (tone_codes <= 4)
    outside_shade = shade_mask & (~face_s)
    if np.any(outside_shade):
        labeled, nlab = ndimage.label(outside_shade)
        for lab in range(1, nlab + 1):
            comp = labeled == lab
            if int(comp.sum()) <= 2:
                tone_codes[comp] = 0
                tone_grid[comp] = 0.0

    # Shade interface links: same row (H) or compatible neighbor codes
    link_h = np.zeros((h_s, max(0, w_s - 1)), dtype=bool)
    link_v = np.zeros((max(0, h_s - 1), w_s), dtype=bool)
    for y in range(h_s):
        for x in range(w_s - 1):
            a, b = int(tone_codes[y, x]), int(tone_codes[y, x + 1])
            if a < 1 or a > 4 or b < 1 or b > 4:
                continue
            if face_s[y, x] != face_s[y, x + 1]:
                continue
            # Compatible density (allow ±1)
            if abs(a - b) <= 1:
                link_h[y, x] = True
    for y in range(h_s - 1):
        for x in range(w_s):
            a, b = int(tone_codes[y, x]), int(tone_codes[y + 1, x])
            if a < 1 or a > 4 or b < 1 or b > 4:
                continue
            if face_s[y, x] != face_s[y + 1, x]:
                continue
            # Vertical links only for denser codes (cross-band rare)
            if a >= 3 and b >= 3 and abs(a - b) <= 1:
                link_v[y, x] = True

    # Edge interface degree (for prune): neighbors both above edge thresh
    edge_link_h = np.zeros((h_s, max(0, w_s - 1)), dtype=bool)
    edge_link_v = np.zeros((max(0, h_s - 1), w_s), dtype=bool)
    eth = 0.18
    for y in range(h_s):
        for x in range(w_s - 1):
            if mesh_edge[y, x] >= eth and mesh_edge[y, x + 1] >= eth:
                # Similar gradient → continuous structure
                dot = float(grad_x[y, x] * grad_x[y, x + 1] + grad_y[y, x] * grad_y[y, x + 1])
                if dot >= 0.15:
                    edge_link_h[y, x] = True
    for y in range(h_s - 1):
        for x in range(w_s):
            if mesh_edge[y, x] >= eth and mesh_edge[y + 1, x] >= eth:
                dot = float(grad_x[y, x] * grad_x[y + 1, x] + grad_y[y, x] * grad_y[y + 1, x])
                if dot >= 0.15:
                    edge_link_v[y, x] = True

    edge_degree = np.zeros((h_s, w_s), dtype=np.uint8)
    if w_s > 1:
        edge_degree[:, :-1] += edge_link_h.astype(np.uint8)
        edge_degree[:, 1:] += edge_link_h.astype(np.uint8)
    if h_s > 1:
        edge_degree[:-1, :] += edge_link_v.astype(np.uint8)
        edge_degree[1:, :] += edge_link_v.astype(np.uint8)

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
        "mesh_ink": ink_s.astype(np.float32),
        "mesh_edge": mesh_edge,
        "mesh_face": face_s.astype(np.uint8),
        "mesh_grad_x": grad_x,
        "mesh_grad_y": grad_y,
        "link_h": link_h,
        "link_v": link_v,
        "edge_degree": edge_degree,
        "mesh_cell_px": float(sc),
    }


def _walk_horizontal_runs(
    codes: np.ndarray,
    link_h: np.ndarray,
    *,
    min_code: int,
    max_code: int,
) -> list[tuple[int, int, int, int]]:
    """Return list of (y, x0, x1_inclusive, max_code_in_run)."""
    h_s, w_s = codes.shape
    runs: list[tuple[int, int, int, int]] = []
    for y in range(h_s):
        x = 0
        while x < w_s:
            c = int(codes[y, x])
            if c < min_code or c > max_code:
                x += 1
                continue
            x0 = x
            cmax = c
            x += 1
            while x < w_s and link_h[y, x - 1] and min_code <= int(codes[y, x]) <= max_code:
                cmax = max(cmax, int(codes[y, x]))
                x += 1
            runs.append((y, x0, x - 1, cmax))
    return runs


def strokes_from_mesh_walks(
    mesh: dict[str, Any],
    *,
    img_w: int,
    img_h: int,
    page_w: float,
    page_h: float,
    style: str = "hatch",
    jitter: float = 0.03,
    seed: int = 1,
    max_paths: int = 4000,
) -> list[list[tuple[float, float]]]:
    """
    Shade strokes by walking H interfaces (continuous hatch bands).

    Codes 1–3: parallel hatch only. Code 4: scribble along the run (scribble style)
    or denser parallel hatch (hatch style). Code 5: skip.
    """
    codes = np.asarray(mesh["tone_codes"], dtype=np.uint8)
    link_h = np.asarray(mesh["link_h"], dtype=bool)
    hs = float(mesh["tone_cell_px"])
    h_s, w_s = codes.shape
    table = _make_perlin_table(seed)
    out_px: list[list[tuple[float, float]]] = []

    runs = _walk_horizontal_runs(codes, link_h, min_code=1, max_code=4)
    # Prefer longer face runs first (path budget)
    face = np.asarray(mesh.get("mesh_face"), dtype=np.uint8) > 0 if mesh.get("mesh_face") is not None else None

    def run_score(r: tuple[int, int, int, int]) -> float:
        y, x0, x1, cmax = r
        length = x1 - x0 + 1
        bonus = 0.0
        if face is not None and face[y, x0]:
            bonus = 40.0
        return length * 2.0 + cmax + bonus

    runs.sort(key=run_score, reverse=True)

    for y, x0, x1, cmax in runs:
        if len(out_px) >= max_paths:
            break
        length = x1 - x0 + 1
        if length < 1:
            continue
        # Skip tiny outside runs
        if length == 1 and (face is None or not face[y, x0]):
            continue

        x_left = x0 * hs
        x_right = (x1 + 1) * hs
        y_base = y * hs

        # Line count / offsets by code (no per-cell X stamps)
        if cmax == 1:
            offsets = [0.45]
        elif cmax == 2:
            offsets = [0.38]
        elif cmax == 3:
            offsets = [0.28, 0.62]
        else:  # 4
            offsets = [0.22, 0.50, 0.78] if style == "hatch" else [0.35, 0.65]

        if style == "scribble" and cmax >= 3:
            ink = 0.35 + 0.12 * (cmax - 3)
            amp = hs * (0.12 + 0.28 * ink)
            n_pts = max(4, length * 2)
            for oi, off in enumerate(offsets[:2]):
                pts: list[tuple[float, float]] = []
                for k in range(n_pts + 1):
                    t = k / n_pts
                    px = x_left + t * (x_right - x_left)
                    wave = amp * math.sin(t * math.pi * (1.2 + length * 0.08 + ink))
                    jx = hs * jitter * (_perlin_noise(table, y * 0.2, oi, k * 0.25) - 0.5)
                    jy = hs * jitter * (_perlin_noise(table, y * 0.2, oi, k * 0.25 + 2) - 0.5)
                    pts.append((px + jx, y_base + off * hs + wave + jy))
                if len(pts) >= 2:
                    out_px.append(pts)
                    if len(out_px) >= max_paths:
                        break
            continue

        for oi, off in enumerate(offsets):
            y_line = y_base + off * hs
            # Light stagger on odd runs for hand-drawn feel
            if (y + oi) % 2:
                y_line += hs * 0.04
            pts = [(x_left, y_line), (x_right, y_line)]
            # Code 3: one light diagonal accent on longer face runs only
            if cmax >= 3 and length >= 3 and style == "hatch" and oi == 0 and (y % 3 == 0):
                mid = (x_left + x_right) * 0.5
                out_px.append([(mid - hs * 0.4, y_base), (mid + hs * 0.4, y_base + hs)])
            amount = hs * jitter * 0.15
            jpts = []
            for j, (px, py) in enumerate(pts):
                jx = amount * (_perlin_noise(table, y * 0.3 + oi, j, 1.0) - 0.5) * 2.0
                jy = amount * (_perlin_noise(table, y * 0.3 + oi, j, 2.0) - 0.5) * 2.0
                jpts.append((px + jx, py + jy))
            if math.hypot(jpts[-1][0] - jpts[0][0], jpts[-1][1] - jpts[0][1]) >= hs * 0.5:
                out_px.append(jpts)
            if len(out_px) >= max_paths:
                break

    return polylines_to_mm(
        out_px[:max_paths],
        img_w=img_w,
        img_h=img_h,
        page_w=page_w,
        page_h=page_h,
    )


def prune_edges_with_mesh(
    contours_px: list[list[tuple[float, float]]],
    mesh: dict[str, Any],
    *,
    outside_min_len: float = 64.0,
    inside_min_len: float = 12.0,
) -> list[list[tuple[float, float]]]:
    """
    Drop peripheral edge islands that don't sit on mesh edge structure.

    Inside face: keep if length ok OR mesh edge_degree high along path.
    Outside face: require longer path AND average mesh_edge above floor.
    """
    codes_face = np.asarray(mesh.get("mesh_face"), dtype=np.uint8)
    mesh_edge = np.asarray(mesh["mesh_edge"], dtype=np.float32)
    edge_degree = np.asarray(mesh["edge_degree"], dtype=np.uint8)
    hs = float(mesh["tone_cell_px"])
    h_s, w_s = mesh_edge.shape
    img_h, img_w = mesh["img_shape"]

    def sample_cell(x: float, y: float) -> tuple[int, int]:
        cx = int(np.clip(x / hs, 0, w_s - 1))
        cy = int(np.clip(y / hs, 0, h_s - 1))
        return cy, cx

    out: list[list[tuple[float, float]]] = []
    for c in contours_px:
        if len(c) < 2:
            continue
        plen = 0.0
        for i in range(1, len(c)):
            plen += math.hypot(c[i][0] - c[i - 1][0], c[i][1] - c[i - 1][1])
        step = max(1, len(c) // 12)
        edge_vals = []
        deg_vals = []
        face_hits = 0
        n = 0
        for x, y in c[::step]:
            cy, cx = sample_cell(x, y)
            edge_vals.append(float(mesh_edge[cy, cx]))
            deg_vals.append(int(edge_degree[cy, cx]))
            if codes_face.size and codes_face[cy, cx]:
                face_hits += 1
            n += 1
        face_frac = face_hits / max(1, n)
        mean_edge = float(np.mean(edge_vals)) if edge_vals else 0.0
        mean_deg = float(np.mean(deg_vals)) if deg_vals else 0.0

        if face_frac >= 0.35:
            if plen >= inside_min_len or mean_deg >= 1.0:
                out.append(c)
        else:
            # Outside: kill floaters with weak mesh support
            if plen >= outside_min_len and mean_edge >= 0.12 and mean_deg >= 0.5:
                out.append(c)
            elif plen >= outside_min_len * 1.6 and mean_edge >= 0.22:
                out.append(c)
    return out

