"""
Linedraw-style contour + tone hatch extraction for pen plotters.

Clean reimplementation inspired by Lingdong Huang's linedraw
(https://github.com/LingDong-/linedraw), MIT License.
Copyright (c) 2017 Lingdong Huang — algorithm attribution retained.

No OpenCV dependency: Sobel magnitude + hysteresis-lite via numpy/Pillow.
Portrait-aware: midtone hatch skips flat dark backgrounds.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from shapely.geometry import LineString

from botdraw.styles.image_utils import map_to_page

# --- Minimal Perlin (p5.js-style), seeded for reproducibility ----------------

_PERLIN_YWRAPB = 4
_PERLIN_YWRAP = 1 << _PERLIN_YWRAPB
_PERLIN_ZWRAPB = 8
_PERLIN_ZWRAP = 1 << _PERLIN_ZWRAPB
_PERLIN_SIZE = 4095


def _make_perlin_table(seed: int) -> list[float]:
    m = 4294967296.0
    a = 1664525.0
    c = 1013904223.0
    z = float(seed & 0xFFFFFFFF)
    out: list[float] = []
    for _ in range(_PERLIN_SIZE + 1):
        z = (a * z + c) % m
        out.append(z / m)
    return out


def _scaled_cosine(i: float) -> float:
    return 0.5 * (1.0 - math.cos(i * math.pi))


def _perlin_noise(table: list[float], x: float, y: float = 0.0, z: float = 0.0) -> float:
    if x < 0:
        x = -x
    if y < 0:
        y = -y
    if z < 0:
        z = -z
    xi, yi, zi = int(x), int(y), int(z)
    xf, yf, zf = x - xi, y - yi, z - zi
    r = 0.0
    ampl = 0.5
    for _ in range(4):
        of = xi + (yi << _PERLIN_YWRAPB) + (zi << _PERLIN_ZWRAPB)
        rxf = _scaled_cosine(xf)
        ryf = _scaled_cosine(yf)
        n1 = table[of & _PERLIN_SIZE]
        n1 += rxf * (table[(of + 1) & _PERLIN_SIZE] - n1)
        n2 = table[(of + _PERLIN_YWRAP) & _PERLIN_SIZE]
        n2 += rxf * (table[(of + _PERLIN_YWRAP + 1) & _PERLIN_SIZE] - n2)
        n1 += ryf * (n2 - n1)
        of += _PERLIN_ZWRAP
        n2 = table[of & _PERLIN_SIZE]
        n2 += rxf * (table[(of + 1) & _PERLIN_SIZE] - n2)
        n3 = table[(of + _PERLIN_YWRAP) & _PERLIN_SIZE]
        n3 += rxf * (table[(of + _PERLIN_YWRAP + 1) & _PERLIN_SIZE] - n3)
        n2 += ryf * (n3 - n2)
        n1 += _scaled_cosine(zf) * (n2 - n1)
        r += n1 * ampl
        ampl *= 0.5
        xi <<= 1
        xf *= 2
        yi <<= 1
        yf *= 2
        zi <<= 1
        zf *= 2
        if xf >= 1.0:
            xi += 1
            xf -= 1
        if yf >= 1.0:
            yi += 1
            yf -= 1
        if zf >= 1.0:
            zi += 1
            zf -= 1
    return r


def autocontrast_lum(lum: np.ndarray, cutoff: float = 10.0) -> np.ndarray:
    """Return uint8 L image after mild autocontrast."""
    g = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L")
    g = ImageOps.autocontrast(g, cutoff=cutoff)
    return np.asarray(g, dtype=np.uint8)


def edge_bitmap(lum: np.ndarray, *, low: float = 80.0, high: float = 160.0) -> np.ndarray:
    """Sobel magnitude + dual-threshold (Canny-lite). Returns bool HxW mask."""
    g = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L")
    g = g.filter(ImageFilter.GaussianBlur(radius=1.0))
    arr = np.asarray(g, dtype=np.float32)
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
    from numpy.lib.stride_tricks import sliding_window_view

    pad = np.pad(arr, 1, mode="edge")
    windows = sliding_window_view(pad, (3, 3))
    gx = np.tensordot(windows, kx, axes=([2, 3], [0, 1]))
    gy = np.tensordot(windows, ky, axes=([2, 3], [0, 1]))
    mag = np.hypot(gx, gy)
    mmax = float(mag.max()) or 1.0
    mag_n = mag * (255.0 / mmax)
    strong = mag_n >= high
    weak = (mag_n >= low) & (~strong)
    strong_pad = np.pad(strong, 1, mode="constant")
    keep_weak = np.zeros_like(weak)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            keep_weak |= weak & strong_pad[1 + dy : 1 + dy + weak.shape[0], 1 + dx : 1 + dx + weak.shape[1]]
    return strong | keep_weak


def _getdots(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    h, w = mask.shape
    dots: list[list[tuple[int, int]]] = []
    for y in range(h):
        row: list[tuple[int, int]] = []
        x = 0
        while x < w:
            if not mask[y, x]:
                x += 1
                continue
            x0 = x
            while x < w and mask[y, x]:
                x += 1
            row.append((x0, x - x0 - 1))
        dots.append(row)
    return dots


def _connectdots(dots: list[list[tuple[int, int]]]) -> list[list[tuple[int, int]]]:
    contours: list[list[tuple[int, int]]] = []
    for y, row in enumerate(dots):
        for x, _v in row:
            if y == 0:
                contours.append([(x, y)])
                continue
            closest = -1
            cdist = 100
            for x0, _v0 in dots[y - 1]:
                d = abs(x0 - x)
                if d < cdist:
                    cdist = d
                    closest = x0
            if cdist > 3:
                contours.append([(x, y)])
            else:
                found = False
                for c in contours:
                    if c and c[-1] == (closest, y - 1):
                        c.append((x, y))
                        found = True
                        break
                if not found:
                    contours.append([(x, y)])
        contours = [c for c in contours if not (c and c[-1][1] < y - 1 and len(c) < 4)]
    return contours


def _merge_near_endpoints(
    contours: list[list[tuple[float, float]]],
    dist_thresh: float = 8.0,
) -> list[list[tuple[float, float]]]:
    alive = [list(c) for c in contours if len(c) > 1]
    changed = True
    while changed:
        changed = False
        for i in range(len(alive)):
            if not alive[i]:
                continue
            for j in range(len(alive)):
                if i == j or not alive[j]:
                    continue
                a, b = alive[i], alive[j]
                dx = a[-1][0] - b[0][0]
                dy = a[-1][1] - b[0][1]
                if math.hypot(dx, dy) < dist_thresh:
                    alive[i] = a + b
                    alive[j] = []
                    changed = True
        alive = [c for c in alive if len(c) > 1]
    return alive


def _subsample(contours: list[list[tuple[float, float]]], step: int) -> list[list[tuple[float, float]]]:
    step = max(1, int(step))
    out: list[list[tuple[float, float]]] = []
    for c in contours:
        if len(c) < 2:
            continue
        pts = [c[j] for j in range(0, len(c), step)]
        if pts[-1] != c[-1]:
            pts.append(c[-1])
        if len(pts) >= 2:
            out.append(pts)
    return out


def _dp_simplify_px(
    contours: list[list[tuple[float, float]]],
    tolerance: float,
) -> list[list[tuple[float, float]]]:
    if tolerance <= 0:
        return contours
    out: list[list[tuple[float, float]]] = []
    for c in contours:
        if len(c) < 3:
            if len(c) >= 2:
                out.append(c)
            continue
        try:
            simple = list(LineString(c).simplify(float(tolerance), preserve_topology=False).coords)
            if len(simple) >= 2:
                out.append([(float(a), float(b)) for a, b in simple])
        except Exception:
            out.append(c)
    return out


def _apply_jitter(
    contours: list[list[tuple[float, float]]],
    *,
    amount_px: float,
    seed: int,
) -> list[list[tuple[float, float]]]:
    if amount_px <= 0:
        return contours
    table = _make_perlin_table(seed)
    out: list[list[tuple[float, float]]] = []
    for i, c in enumerate(contours):
        pts: list[tuple[float, float]] = []
        for j, (x, y) in enumerate(c):
            jx = amount_px * (_perlin_noise(table, i * 0.5, j * 0.1, 1.0) - 0.5) * 2.0
            jy = amount_px * (_perlin_noise(table, i * 0.5, j * 0.1, 2.0) - 0.5) * 2.0
            pts.append((x + jx, y + jy))
        out.append(pts)
    return out


def contours_from_lum(
    lum: np.ndarray,
    *,
    simplify: int = 2,
    jitter: float = 0.04,
    seed: int = 0,
    max_paths: int = 2000,
) -> tuple[list[list[tuple[float, float]]], np.ndarray]:
    """
    Dual-axis linedraw contours in pixel space.

    `simplify` controls post-trace strength (1=finest). Working resolution stays
    high except for aggressive simplify (>=3) used by booth-fast.
    """
    h0, w0 = lum.shape
    strength = max(1, int(simplify))
    # Only downsample for aggressive simplify; otherwise trace near full res
    if strength >= 3:
        sc = 2
    else:
        sc = 1
    w_s = max(8, w0 // sc)
    h_s = max(8, int(round(h0 * (w_s / w0))))
    small = np.asarray(
        Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.LANCZOS
        ),
        dtype=np.float32,
    )
    small_u8 = autocontrast_lum(small, cutoff=10.0)
    mask = edge_bitmap(small_u8.astype(np.float32))
    edge_full = np.asarray(
        Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
            (w0, h0), Image.Resampling.NEAREST
        ),
        dtype=np.float32,
    )

    dots1 = _getdots(mask)
    c1 = _connectdots(dots1)
    pil = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    pil2 = pil.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    mask2 = np.asarray(pil2, dtype=np.uint8) > 127
    dots2 = _getdots(mask2)
    c2 = _connectdots(dots2)
    c2_mapped: list[list[tuple[int, int]]] = [[(p[1], p[0]) for p in c] for c in c2]

    contours: list[list[tuple[float, float]]] = []
    for c in c1 + c2_mapped:
        if len(c) > 1:
            contours.append([(float(x), float(y)) for x, y in c])

    contours = _merge_near_endpoints(contours, dist_thresh=8.0)
    # Finer subsample than classic linedraw's every-8
    step = max(2, 8 // max(1, 4 - strength + 1))
    if strength == 1:
        step = 2
    elif strength == 2:
        step = 3
    else:
        step = 4
    contours = _subsample(contours, step=step)
    scaled: list[list[tuple[float, float]]] = [[(x * sc, y * sc) for x, y in c] for c in contours]

    # Douglas-Peucker in px (tolerance grows slightly with strength)
    tol = 0.85 if strength <= 1 else (1.2 if strength == 2 else 1.8)
    scaled = _dp_simplify_px(scaled, tolerance=tol * float(sc))

    amount = 6.0 * float(jitter)  # milder than classic ~10px
    scaled = _apply_jitter(scaled, amount_px=amount, seed=seed)

    def plen(pts: Sequence[tuple[float, float]]) -> float:
        t = 0.0
        for i in range(1, len(pts)):
            t += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        return t

    scaled.sort(key=plen, reverse=True)
    return scaled[:max_paths], edge_full


def _midtone_hatch_mask(small: np.ndarray) -> np.ndarray:
    """
    True where hatch is allowed: midtones with local structure.

    Skips flat near-black (dark walls) and near-white highlights that classic
    linedraw would either over-hatch or leave empty incorrectly on dark-bg photos.
    """
    arr = small.astype(np.float32)
    lo = float(np.percentile(arr, 18))
    hi = float(np.percentile(arr, 88))
    # Absolute clamps after autocontrast
    lo = max(35.0, min(lo, 90.0))
    hi = min(210.0, max(hi, 140.0))
    tone = (arr >= lo) & (arr <= hi)

    # Local variance: reject flat regions (uniform wall)
    pad = np.pad(arr, 1, mode="edge")
    from numpy.lib.stride_tricks import sliding_window_view

    win = sliding_window_view(pad, (3, 3))
    local_std = win.reshape(win.shape[0], win.shape[1], -1).std(axis=2)
    structured = local_std >= 4.5
    return tone & structured


def hatch_from_lum(
    lum: np.ndarray,
    *,
    hatch_size: int = 16,
    jitter: float = 0.04,
    seed: int = 1,
    max_paths: int = 4000,
) -> list[list[tuple[float, float]]]:
    """Portrait midtone hatch. hatch_size<=0 → empty. Skips flat dark background."""
    sc = int(hatch_size)
    if sc <= 0:
        return []
    h0, w0 = lum.shape
    w_s = max(4, w0 // sc)
    h_s = max(4, int(round(h0 * (w_s / w0))))
    small = np.asarray(
        Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.LANCZOS
        ),
        dtype=np.uint8,
    )
    small = autocontrast_lum(small.astype(np.float32), cutoff=10.0)
    allow = _midtone_hatch_mask(small)

    lg1: list[list[tuple[float, float]]] = []
    lg2: list[list[tuple[float, float]]] = []
    hs = float(sc)
    # Density relative to midtone band (darker midtones → denser)
    vals = small.astype(np.float32)
    for y0 in range(h_s):
        for x0 in range(w_s):
            if not allow[y0, x0]:
                continue
            v = float(vals[y0, x0])
            x = x0 * hs
            y = y0 * hs
            # Map midtone range to density tiers (not absolute near-black)
            if v > 160:
                # light midtone — sparse
                lg1.append([(x, y + hs / 4), (x + hs, y + hs / 4)])
            elif v > 100:
                lg1.append([(x, y + hs / 4), (x + hs, y + hs / 4)])
                lg2.append([(x + hs, y), (x, y + hs)])
            else:
                lg1.append([(x, y + hs / 4), (x + hs, y + hs / 4)])
                lg1.append([(x, y + hs / 2 + hs / 4), (x + hs, y + hs / 2 + hs / 4)])
                lg2.append([(x + hs, y), (x, y + hs)])

    def join_collinear(lines: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
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
                    if lines[i][-1] == lines[j][0]:
                        lines[i] = lines[i] + lines[j][1:]
                        lines[j] = []
                        changed = True
            lines = [l for l in lines if len(l) > 0]
        return lines

    lines = join_collinear(lg1) + join_collinear(lg2)
    table = _make_perlin_table(seed)
    amount = float(sc) * float(jitter) * 0.5
    out: list[list[tuple[float, float]]] = []
    for i, line in enumerate(lines):
        pts: list[tuple[float, float]] = []
        for j, (x, y) in enumerate(line):
            jx = amount * (_perlin_noise(table, i * 0.5, j * 0.1, 1.0) - 0.5) * 2.0
            jy = amount * (_perlin_noise(table, i * 0.5, j * 0.1, 2.0) - 0.5) * 2.0
            pts.append((x + jx, y + jy))
        if len(pts) >= 2:
            out.append(pts)
    return out[:max_paths]


def polylines_to_mm(
    polylines_px: list[list[tuple[float, float]]],
    *,
    img_w: int,
    img_h: int,
    page_w: float,
    page_h: float,
) -> list[list[tuple[float, float]]]:
    out: list[list[tuple[float, float]]] = []
    for pts in polylines_px:
        mm = [map_to_page(x, y, img_w=img_w, img_h=img_h, page_w=page_w, page_h=page_h) for x, y in pts]
        if len(mm) >= 2:
            out.append([(float(a), float(b)) for a, b in mm])
    return out


def linedraw_edges_and_hatch(
    lum: np.ndarray,
    *,
    page_w: float,
    page_h: float,
    contour_simplify: int = 2,
    hatch_size: int = 16,
    jitter: float = 0.04,
    seed: int = 0,
    max_edge_paths: int = 2000,
    max_hatch_paths: int = 4000,
) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]], np.ndarray]:
    """Full linedraw-style pass → (edge_mm, hatch_mm, edge_map)."""
    h, w = lum.shape
    lum_u8 = autocontrast_lum(lum, cutoff=10.0).astype(np.float32)
    contours_px, edge_map = contours_from_lum(
        lum_u8,
        simplify=contour_simplify,
        jitter=jitter,
        seed=seed,
        max_paths=max_edge_paths,
    )
    hatch_px = hatch_from_lum(
        lum_u8,
        hatch_size=hatch_size,
        jitter=jitter,
        seed=seed + 1,
        max_paths=max_hatch_paths,
    )
    edges_mm = polylines_to_mm(contours_px, img_w=w, img_h=h, page_w=page_w, page_h=page_h)
    hatch_mm = polylines_to_mm(hatch_px, img_w=w, img_h=h, page_w=page_w, page_h=page_h)
    return edges_mm, hatch_mm, edge_map
