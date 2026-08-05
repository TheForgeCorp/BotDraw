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
    lum_raw: np.ndarray | None = None,
    subject_mask: np.ndarray | None = None,
    shade_prior: np.ndarray | None = None,
    ink_is_authoritative: bool = False,
) -> dict[str, Any]:
    """
    Build mesh arrays + interface adjacency.

    `lum_raw` (unposterized luma) feeds the focus/sharpness measures;
    posterization fabricates hard steps that read as fake in-focus edges.

    `subject_mask` (person matte [0..1], full res) replaces the focus/bokeh
    heuristics as the outside-subject gate when provided. `shade_prior`
    (bool, full res) marks solid-dark regions the line model drew as fill —
    those cells are forced to deep shade for the tone channel.

    Returns dict compatible with tone_grid fields plus mesh_edge / mesh_face /
    link_h (bool array for shade joins) and edge_degree (for edge prune).
    """
    sc = max(4, int(cell_px))
    h0, w0 = lum.shape
    if lum_raw is None or np.asarray(lum_raw).shape != (h0, w0):
        lum_raw = lum
    lum_raw = np.asarray(lum_raw, dtype=np.float32)
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

    # Per-cell focus measure: high-frequency energy of the source luma. Bokeh
    # backgrounds are smooth, so their cells score low and get suppressed.
    lum8 = np.clip(lum_raw, 0, 255).astype(np.uint8)
    lum_blur = np.asarray(
        Image.fromarray(lum8, mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(1.5, sc * 0.5))
        ),
        dtype=np.float32,
    )
    hf_full = np.abs(lum_raw - lum_blur)
    hf_s = np.asarray(
        Image.fromarray(np.clip(hf_full, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.BOX
        ),
        dtype=np.float32,
    )
    # Absolute units (luma delta): in-focus texture measures ~4–17, bokeh ~0–4.
    focus = hf_s.astype(np.float32)

    # Boundary sharpness: peak gradient relative to local luma range (edge
    # width). A sharp edge packs its step into 1–2 px (ratio near 1); a bokeh
    # edge spreads the same step over many px (ratio well under 0.2).
    gy_f, gx_f = np.gradient(lum_raw)
    gm_max = ndimage.maximum_filter(np.hypot(gx_f, gy_f), size=sc)
    rng = ndimage.maximum_filter(lum_raw, size=2 * sc) - ndimage.minimum_filter(lum_raw, size=2 * sc)
    ratio_full = np.clip(gm_max / (rng + 8.0), 0.0, 1.0)
    sharp = np.asarray(
        Image.fromarray((ratio_full * 255.0).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.BOX
        ),
        dtype=np.float32,
    ) / 255.0

    # Gradient at mesh res (for optional hatch direction / edge interface)
    gy, gx = np.gradient(lum_s.astype(np.float32))
    gmag = np.hypot(gx, gy) + 1e-6
    grad_x = (gx / gmag).astype(np.float32)
    grad_y = (gy / gmag).astype(np.float32)

    if ink_is_authoritative:
        # Ink already encodes an artist's judgment (neural line raster):
        # shade wherever it drew, skip only where it left paper.
        allow = ink_s >= 0.10
    else:
        u8 = autocontrast_lum(lum_s, cutoff=6.0)
        allow = _midtone_hatch_mask(u8.astype(np.float32))
    face = face_roi_mask(lum)
    face_s = np.asarray(
        Image.fromarray((face.astype(np.uint8) * 255), mode="L").resize(
            (w_s, h_s), Image.Resampling.NEAREST
        ),
        dtype=np.uint8,
    ) > 127

    if not ink_is_authoritative:
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

    # Outside-subject suppression: prefer the semantic person matte when the
    # caller has one; otherwise fall back to focus/sharpness heuristics that
    # damp bokeh shapes (soft boundaries, low texture) outside the face ROI.
    subj_s = None
    if subject_mask is not None:
        subj_s = np.asarray(
            Image.fromarray(
                (np.clip(np.asarray(subject_mask, dtype=np.float32), 0, 1) * 255).astype(np.uint8),
                mode="L",
            ).resize((w_s, h_s), Image.Resampling.BILINEAR),
            dtype=np.float32,
        ) / 255.0 > 0.5
    if subj_s is not None:
        defocus = ~subj_s
        mesh_edge = np.where(defocus, mesh_edge * 0.2, mesh_edge).astype(np.float32)
    else:
        defocus = (~face_s) & ((focus < 3.25) | (sharp < 0.12))
        sharp_scale = np.clip((sharp - 0.08) / 0.15, 0.25, 1.0).astype(np.float32)
        mesh_edge = np.where(~face_s, mesh_edge * sharp_scale, mesh_edge).astype(np.float32)

    # Cell-size-aware structure gate: a physical edge stroke ~4px wide gives
    # occupancy ≈ 4/cell. Fixed thresholds flood fine meshes (5px → quarter of
    # the grid went code 5), so scale by cell size instead.
    edge_gate = float(min(0.85, 3.9 / sc))
    edge_strong = mesh_edge >= edge_gate

    max_code = int(np.clip(max_code, 1, 5))
    ink = ink_s.astype(np.float32)

    # Vectorized code binning (face uses relative bins for dark-bg selfies)
    face_bins = np.array([0.14, 0.28, 0.40, 0.55, 0.72], dtype=np.float32)
    out_bins = np.array([0.18, 0.30, 0.45, 0.58, 0.72], dtype=np.float32)
    codes_face = np.digitize(ink, face_bins).astype(np.uint8)  # 0..5
    codes_out = np.digitize(ink, out_bins).astype(np.uint8)
    # Deep shade stays drawable: darkness alone never makes a structure cell
    # (code 5 is assigned only from edge support below)
    deep_code = 4 if max_code >= 4 else 3
    codes_face[codes_face == 5] = deep_code
    codes_out[codes_out == 5] = deep_code
    tone_codes = np.where(face_s, codes_face, codes_out).astype(np.uint8)

    # Skips: disallowed cells, thin outside ink (walls), defocused background
    if ink_is_authoritative:
        skip = (~allow) | defocus
    else:
        skip = (~allow) | ((~face_s) & (ink < 0.28)) | defocus
    tone_codes[skip] = 0
    # Structure cells: leave to edges. With authoritative ink the drawing has
    # lines and tone coexisting, so edge cells must not punch shade holes.
    if not ink_is_authoritative:
        structure = edge_strong & (ink >= 0.40) & (~skip)
        tone_codes[structure] = 5
    # Clamp shade codes to max_code (code 5 untouched)
    shade = (tone_codes >= 1) & (tone_codes <= 4)
    tone_codes[shade & (tone_codes > max_code)] = max_code

    # Solid-dark prior (line model drew fill here): rescue cells the skip
    # heuristics dropped, but keep the luminance grading so large masses read
    # as tone, not uniform maximum density.
    if shade_prior is not None:
        prior_s = np.asarray(
            Image.fromarray(
                (np.asarray(shade_prior, dtype=bool).astype(np.uint8) * 255), mode="L"
            ).resize((w_s, h_s), Image.Resampling.BOX),
            dtype=np.float32,
        ) / 255.0 > 0.5
        boost = prior_s & (tone_codes == 0)
        graded = np.where(ink >= 0.72, deep_code, 3).astype(np.uint8)
        tone_codes[boost] = np.minimum(graded[boost], max_code)

    tone_grid = np.where(tone_codes > 0, ink, 0.0).astype(np.float32)

    # Kill small outside-face shade islands (checkerboard shirt noise)
    outside_shade = (tone_codes >= 1) & (tone_codes <= 4) & (~face_s)
    if np.any(outside_shade):
        labeled, nlab = ndimage.label(outside_shade)
        if nlab:
            sizes = ndimage.sum(outside_shade, labeled, index=np.arange(1, nlab + 1))
            small = np.isin(labeled, np.nonzero(sizes <= 4)[0] + 1)
            tone_codes[small] = 0
            tone_grid[small] = 0.0

    # Shade interface links (H): both codes 1–4, same face side, density ±1
    c = tone_codes.astype(np.int16)
    in_band = (c >= 1) & (c <= 4)
    link_h = (
        in_band[:, :-1]
        & in_band[:, 1:]
        & (face_s[:, :-1] == face_s[:, 1:])
        & (np.abs(c[:, :-1] - c[:, 1:]) <= 1)
    )

    # Edge interface degree (for prune): neighbors above thresh + similar gradient
    eth = 0.18
    e_ok = mesh_edge >= eth
    dot_h = grad_x[:, :-1] * grad_x[:, 1:] + grad_y[:, :-1] * grad_y[:, 1:]
    edge_link_h = e_ok[:, :-1] & e_ok[:, 1:] & (dot_h >= 0.15)
    dot_v = grad_x[:-1, :] * grad_x[1:, :] + grad_y[:-1, :] * grad_y[1:, :]
    edge_link_v = e_ok[:-1, :] & e_ok[1:, :] & (dot_v >= 0.15)

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
        "mesh_focus": focus,
        "mesh_sharp": sharp,
        "link_h": link_h,
        "edge_degree": edge_degree,
        "mesh_cell_px": float(sc),
        "edge_gate": edge_gate,
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


# Physical hatch pitch by code (mm between lines) — independent of cell size
_PITCH_MM = {1: 1.7, 2: 1.15, 3: 0.8, 4: 0.55}


def _directional_component_strokes(
    mask: np.ndarray,
    grad_x: np.ndarray,
    grad_y: np.ndarray,
    *,
    cell_px: float,
    pitch_px: float,
    jitter: float,
    table: list[float],
    seed_off: float,
) -> list[list[tuple[float, float]]]:
    """
    Parallel strokes across one shade component, oriented along structure
    (perpendicular to mean gradient) so hair/shirt read as flow, not blocks.
    """
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return []
    # Mean gradient over component → stroke direction is its perpendicular
    gx = float(np.mean(grad_x[ys, xs]))
    gy = float(np.mean(grad_y[ys, xs]))
    gnorm = math.hypot(gx, gy)
    if gnorm < 0.25:
        # Incoherent gradient: fixed sketchy diagonal
        dx, dy = math.cos(math.radians(-28.0)), math.sin(math.radians(-28.0))
    else:
        dx, dy = -gy / gnorm, gx / gnorm
    nx, ny = -dy, dx  # normal (line spacing direction)

    cx = (float(np.mean(xs)) + 0.5) * cell_px
    cy = (float(np.mean(ys)) + 0.5) * cell_px
    # Half-extent along direction / normal
    span = max(
        (xs.max() - xs.min() + 1) * cell_px,
        (ys.max() - ys.min() + 1) * cell_px,
    ) * 0.75
    h_s, w_s = mask.shape

    def in_mask(px: float, py: float) -> bool:
        mxx = int(px / cell_px)
        myy = int(py / cell_px)
        if 0 <= myy < h_s and 0 <= mxx < w_s:
            return bool(mask[myy, mxx])
        return False

    strokes: list[list[tuple[float, float]]] = []
    n_lines = max(1, int(round((2.0 * span) / max(pitch_px, 1e-3))))
    step = cell_px * 0.5
    for li in range(n_lines + 1):
        s = -span + li * (2.0 * span) / max(n_lines, 1)
        ox = cx + nx * s
        oy = cy + ny * s
        run: list[tuple[float, float]] = []
        t = -span
        while t <= span:
            px = ox + dx * t
            py = oy + dy * t
            if in_mask(px, py):
                jx = cell_px * jitter * (_perlin_noise(table, seed_off + li * 0.3, t * 0.05, 1.0) - 0.5) * 2.0
                jy = cell_px * jitter * (_perlin_noise(table, seed_off + li * 0.3, t * 0.05, 2.0) - 0.5) * 2.0
                run.append((px + jx, py + jy))
            else:
                if len(run) >= 3:
                    strokes.append(run)
                run = []
            t += step
        if len(run) >= 3:
            strokes.append(run)
    # Drop stubs shorter than ~1.5 cells
    min_len = cell_px * 1.5
    out = []
    for pts in strokes:
        if math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) >= min_len:
            out.append(pts)
    return out


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
    pitch_mm: dict[int, float] | None = None,
) -> list[list[tuple[float, float]]]:
    """
    Shade strokes by walking H interfaces (continuous hatch bands).

    Line pitch is fixed in mm per code, so a finer mesh does NOT get denser
    ink: coarse cells emit multiple lines per row, fine cells skip rows.
    Codes 1–3: parallel hatch. Code 4: scribble (scribble style) or dense
    parallel (hatch style). Code 5: skip.
    """
    codes = np.asarray(mesh["tone_codes"], dtype=np.uint8)
    link_h = np.asarray(mesh["link_h"], dtype=bool)
    hs = float(mesh["tone_cell_px"])
    cell_mm = float(mesh.get("tone_cell_mm") or 0.0)
    if cell_mm <= 0:
        # Derive from page mapping when caller didn't persist it
        cell_mm = hs * (float(page_w) / max(img_w, 1) + float(page_h) / max(img_h, 1)) * 0.5
    pitches = dict(_PITCH_MM)
    if pitch_mm:
        pitches.update(pitch_mm)
    h_s, w_s = codes.shape
    table = _make_perlin_table(seed)
    out_px: list[list[tuple[float, float]]] = []
    face = np.asarray(mesh.get("mesh_face"), dtype=np.uint8) > 0 if mesh.get("mesh_face") is not None else None

    # Deep shade (code 4) components → direction-following strokes (hair/shirt
    # flow). Consumed cells are removed from the horizontal walk below.
    walk_codes = codes.copy()
    grad_x = mesh.get("mesh_grad_x")
    grad_y = mesh.get("mesh_grad_y")
    if grad_x is not None and grad_y is not None and style == "hatch":
        gx = np.asarray(grad_x, dtype=np.float32)
        gy = np.asarray(grad_y, dtype=np.float32)
        deep = codes == 4
        if np.any(deep):
            labeled, nlab = ndimage.label(deep)
            pitch4 = float(pitches.get(4, 0.55))
            pitch_px4 = pitch4 / max(cell_mm, 1e-3) * hs
            comps = []
            if nlab:
                sizes = ndimage.sum(deep, labeled, index=np.arange(1, nlab + 1))
                # Very large masses read as slabs under one direction; leave
                # them to graded horizontal walks instead.
                comps = [lab + 1 for lab in range(nlab) if 6 <= sizes[lab] <= 300]
            for lab in comps:
                comp = labeled == lab
                strokes = _directional_component_strokes(
                    comp,
                    gx,
                    gy,
                    cell_px=hs,
                    pitch_px=pitch_px4,
                    jitter=jitter,
                    table=table,
                    seed_off=float(lab) * 1.7,
                )
                budget_left = max_paths - len(out_px)
                out_px.extend(strokes[: max(0, budget_left)])
                walk_codes[comp] = 0
                if len(out_px) >= max_paths:
                    break

    runs = _walk_horizontal_runs(walk_codes, link_h, min_code=1, max_code=4)

    def run_score(r: tuple[int, int, int, int]) -> float:
        y, x0, x1, cmax = r
        length = x1 - x0 + 1
        bonus = 0.0
        if face is not None and face[y, x0]:
            bonus = 40.0
        return length * 2.0 + cmax + bonus

    runs.sort(key=run_score, reverse=True)

    def line_offsets(cmax: int, y: int) -> list[float]:
        """Cell-height offsets for this row honoring physical pitch."""
        pitch = float(pitches.get(cmax, 1.0))
        per_row = cell_mm / max(pitch, 1e-3)
        if per_row >= 1.0:
            n = min(3, max(1, int(round(per_row))))
            return [(i + 0.5) / n for i in range(n)]
        # Pitch exceeds cell: emit on every k-th mesh row only
        period = max(1, int(round(pitch / max(cell_mm, 1e-3))))
        return [0.5] if (y % period) == 0 else []

    for y, x0, x1, cmax in runs:
        if len(out_px) >= max_paths:
            break
        length = x1 - x0 + 1
        if length < 1:
            continue
        # Outside face: require longer runs (kills scattered shirt blocks)
        if face is not None and not face[y, x0] and length < 3:
            continue
        if face is None and length == 1:
            continue

        x_left = x0 * hs
        x_right = (x1 + 1) * hs
        y_base = y * hs

        if style == "scribble" and cmax >= 3:
            if not line_offsets(cmax, y):
                continue
            ink = 0.35 + 0.12 * (cmax - 3)
            amp = hs * (0.12 + 0.28 * ink)
            n_pts = max(4, length * 2)
            n_seg = 2 if cmax >= 4 else 1
            for oi in range(n_seg):
                off = 0.35 + 0.3 * oi
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

        offsets = line_offsets(cmax, y)
        for oi, off in enumerate(offsets):
            y_line = y_base + off * hs
            # Light stagger on odd rows for hand-drawn feel
            if (y + oi) % 2:
                y_line += hs * 0.06
            pts = [(x_left, y_line), (x_right, y_line)]
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
        # Code 4 in hatch style: one diagonal accent per few rows for texture
        if (
            style == "hatch"
            and cmax >= 4
            and offsets
            and length >= 2
            and (y % 2 == 0)
            and len(out_px) < max_paths
        ):
            mid = (x_left + x_right) * 0.5
            half = min(hs * 1.2, (x_right - x_left) * 0.25)
            out_px.append([(mid - half, y_base), (mid + half, y_base + hs)])

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
    outside_min_len: float = 88.0,
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
    sharp = mesh.get("mesh_sharp")
    sharp = np.asarray(sharp, dtype=np.float32) if sharp is not None else None
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
        sharp_vals = []
        face_hits = 0
        n = 0
        for x, y in c[::step]:
            cy, cx = sample_cell(x, y)
            edge_vals.append(float(mesh_edge[cy, cx]))
            deg_vals.append(int(edge_degree[cy, cx]))
            if sharp is not None:
                sharp_vals.append(float(sharp[cy, cx]))
            if codes_face.size and codes_face[cy, cx]:
                face_hits += 1
            n += 1
        face_frac = face_hits / max(1, n)
        mean_edge = float(np.mean(edge_vals)) if edge_vals else 0.0
        mean_deg = float(np.mean(deg_vals)) if deg_vals else 0.0
        # No sharpness data (cached vectors): treat as in-focus
        mean_sharp = float(np.mean(sharp_vals)) if sharp_vals else 99.0

        if face_frac >= 0.35:
            if plen >= inside_min_len or mean_deg >= 1.0:
                out.append(c)
        else:
            # Outside: kill floaters with weak mesh support; tiny bbox = blob
            xs_c = [p[0] for p in c]
            ys_c = [p[1] for p in c]
            bbox = max(max(xs_c) - min(xs_c), max(ys_c) - min(ys_c))
            if bbox < hs * 2.2:
                continue
            if plen >= outside_min_len and mean_edge >= 0.15 and mean_deg >= 0.75 and mean_sharp >= 0.13:
                out.append(c)
            elif plen >= outside_min_len * 1.6 and mean_edge >= 0.24 and mean_sharp >= 0.10:
                out.append(c)
    return out

