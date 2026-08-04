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


def edge_bitmap(lum: np.ndarray, *, low: float = 42.0, high: float = 95.0) -> np.ndarray:
    """Sobel magnitude + dual-threshold (Canny-lite). Returns bool HxW mask."""
    g = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L")
    g = g.filter(ImageFilter.GaussianBlur(radius=1.25))
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


def _local_contrast_boost(lum: np.ndarray, *, radius: int = 8, amount: float = 1.35) -> np.ndarray:
    """Unsharp-style local contrast so facial features survive dark-bg autocontrast."""
    u8 = np.clip(lum, 0, 255).astype(np.uint8)
    blur = np.asarray(
        Image.fromarray(u8, mode="L").filter(ImageFilter.GaussianBlur(radius=float(radius))),
        dtype=np.float32,
    )
    base = lum.astype(np.float32)
    out = blur + amount * (base - blur)
    return np.clip(out, 0, 255)


def _trace_edge_chains(mask: np.ndarray, *, min_len: int = 6) -> list[list[tuple[float, float]]]:
    """
    Greedy 8-connected walks on a bool edge mask → polylines in pixel space.

    Prefer endpoints (degree 1), then continue until stuck. Removes used pixels
    so each chain is drawn once. Much denser facial detail than linedraw getdots.
    """
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=np.uint8)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return []
    edge_set = set(zip(xs.tolist(), ys.tolist()))

    neighbors = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))

    def degree(x: int, y: int) -> int:
        n = 0
        for dx, dy in neighbors:
            if (x + dx, y + dy) in edge_set:
                n += 1
        return n

    def walk(x0: int, y0: int) -> list[tuple[float, float]]:
        chain: list[tuple[float, float]] = [(float(x0), float(y0))]
        edge_set.discard((x0, y0))
        visited[y0, x0] = 1
        x, y = x0, y0
        while True:
            best = None
            best_score = -1
            for dx, dy in neighbors:
                nx, ny = x + dx, y + dy
                if (nx, ny) not in edge_set:
                    continue
                # Prefer continuing straight-ish
                score = 2 if abs(dx) + abs(dy) == 1 else 1
                if score > best_score:
                    best_score = score
                    best = (nx, ny)
            if best is None:
                break
            x, y = best
            edge_set.discard((x, y))
            visited[y, x] = 1
            chain.append((float(x), float(y)))
        return chain

    # Endpoints first for long coherent strokes
    endpoints = [(x, y) for x, y in list(edge_set) if degree(x, y) == 1]
    chains: list[list[tuple[float, float]]] = []
    for x, y in endpoints:
        if (x, y) not in edge_set:
            continue
        c = walk(x, y)
        if len(c) >= min_len:
            chains.append(c)

    # Remaining loops / junctions
    while edge_set:
        x, y = next(iter(edge_set))
        c = walk(x, y)
        if len(c) >= min_len:
            chains.append(c)
        elif (x, y) in edge_set:
            edge_set.discard((x, y))
    return chains



def _zhang_suen_thin(mask: np.ndarray, *, max_iter: int = 20) -> np.ndarray:
    """
    Zhang–Suen skeletonization (centerline) on a bool mask — vectorized.

    Produces 1px-wide ridges so chain walks follow stroke centers instead of
    thick jittery edge bands — kdraw/VectorLine idea, numpy-only.
    """
    img = (mask.astype(np.uint8) > 0).astype(np.uint8)
    if int(img.sum()) == 0:
        return mask

    def neighbors(a: np.ndarray):
        # p2..p9 clockwise from north
        p2 = a[:-2, 1:-1]
        p3 = a[:-2, 2:]
        p4 = a[1:-1, 2:]
        p5 = a[2:, 2:]
        p6 = a[2:, 1:-1]
        p7 = a[2:, :-2]
        p8 = a[1:-1, :-2]
        p9 = a[:-2, :-2]
        return p2, p3, p4, p5, p6, p7, p8, p9

    changed = True
    it = 0
    while changed and it < max_iter:
        changed = False
        it += 1
        for step in (0, 1):
            p2, p3, p4, p5, p6, p7, p8, p9 = neighbors(img)
            core = img[1:-1, 1:-1]
            b = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            # transitions 0->1
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            a = np.zeros_like(core, dtype=np.uint8)
            for i in range(8):
                a += ((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8)
            cond = (core == 1) & (b >= 2) & (b <= 6) & (a == 1)
            if step == 0:
                cond &= (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                cond &= (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            if cond.any():
                changed = True
                core[cond] = 0
    return img.astype(bool)


def _spur_prune(mask: np.ndarray, *, min_spur: int = 6) -> np.ndarray:
    """Remove short dangling skeleton branches (spurs)."""
    m = mask.copy()
    neighbors = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
    h, w = m.shape
    ys, xs = np.where(m)
    tips = []
    for x, y in zip(xs.tolist(), ys.tolist()):
        deg = 0
        for dx, dy in neighbors:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and m[ny, nx]:
                deg += 1
        if deg == 1:
            tips.append((x, y))
    for x0, y0 in tips:
        path = [(x0, y0)]
        x, y = x0, y0
        prev = None
        while True:
            nxt = None
            for dx, dy in neighbors:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h and m[ny, nx]):
                    continue
                if prev is not None and (nx, ny) == prev:
                    continue
                nxt = (nx, ny)
                break
            if nxt is None:
                break
            # Stop at junctions
            deg = 0
            for dx, dy in neighbors:
                ax, ay = nxt[0] + dx, nxt[1] + dy
                if 0 <= ax < w and 0 <= ay < h and m[ay, ax]:
                    deg += 1
            path.append(nxt)
            if deg != 2:
                break
            prev, x, y = (x, y), nxt[0], nxt[1]
            if len(path) > min_spur + 2:
                break
        if len(path) <= min_spur:
            for x, y in path:
                deg = sum(
                    1
                    for dx, dy in neighbors
                    if 0 <= x + dx < w and 0 <= y + dy < h and m[y + dy, x + dx]
                )
                if deg <= 2:
                    m[y, x] = False
    return m


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


def _merge_bidirectional(
    contours: list[list[tuple[float, float]]],
    dist_thresh: float = 8.0,
) -> list[list[tuple[float, float]]]:
    """
    Join polylines end-to-end in either orientation (line-weaver continuity).

    Endpoint-only distance checks + spatial buckets; reverse only when merging.
    """
    alive: list[list[tuple[float, float]]] = [list(c) for c in contours if len(c) > 1]
    if len(alive) < 2:
        return alive
    thresh2 = float(dist_thresh) * float(dist_thresh)
    cell = max(float(dist_thresh), 1.0)
    max_rounds = max(64, len(alive) * 2)

    for _ in range(max_rounds):
        buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for i, c in enumerate(alive):
            for end_flag, p in ((0, c[0]), (1, c[-1])):
                key = (int(p[0] // cell), int(p[1] // cell))
                buckets.setdefault(key, []).append((i, end_flag))

        best_d2 = thresh2
        best: tuple[int, int, bool, bool] | None = None
        for (kx, ky), items in buckets.items():
            neigh: list[tuple[int, int]] = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neigh.extend(buckets.get((kx + dx, ky + dy), ()))
            for i, ei in items:
                pi = alive[i][0 if ei == 0 else -1]
                for j, ej in neigh:
                    if i >= j:
                        continue
                    pj = alive[j][0 if ej == 0 else -1]
                    d2 = (pi[0] - pj[0]) ** 2 + (pi[1] - pj[1]) ** 2
                    if d2 >= best_d2:
                        continue
                    # Join so the near endpoints become end(first)+start(second)
                    best_d2 = d2
                    best = (i, j, ei == 0, ej == 1)

        if best is None:
            break
        i, j, rev_i, rev_j = best
        a = list(reversed(alive[i])) if rev_i else alive[i]
        b = list(reversed(alive[j])) if rev_j else alive[j]
        alive[i] = a + b
        alive.pop(j)

    return [c for c in alive if len(c) > 1]


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
    Portrait edge chains: silhouette structure + face-feature pass.

    `simplify` controls post-trace strength (1=finest).
    """
    h0, w0 = lum.shape
    strength = max(1, int(simplify))
    sc = 2 if strength >= 3 else 1
    w_s = max(8, w0 // sc)
    h_s = max(8, int(round(h0 * (w_s / w0))))
    small = np.asarray(
        Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.LANCZOS
        ),
        dtype=np.float32,
    )
    boosted = _local_contrast_boost(small, radius=max(3, 5 // sc), amount=1.55)
    small_u8 = autocontrast_lum(boosted, cutoff=5.0)

    from numpy.lib.stride_tricks import sliding_window_view

    # Silhouette / high-contrast structure
    mask_hi = edge_bitmap(small_u8.astype(np.float32), low=58.0, high=125.0)
    # Face interior: bright after autocontrast (skin/glasses area)
    face = small_u8.astype(np.float32) >= 100.0
    pad_f = np.pad(face.astype(np.uint8), 2, mode="constant")
    face_d = sliding_window_view(pad_f, (5, 5)).max(axis=(2, 3)).astype(bool)
    # Soft facial features — only inside face ROI
    mask_face = edge_bitmap(small_u8.astype(np.float32), low=28.0, high=65.0) & face_d
    mask = mask_hi | mask_face

    edge_full = np.asarray(
        Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
            (w0, h0), Image.Resampling.NEAREST
        ),
        dtype=np.float32,
    )

    # Centerline: thin at capped working res for speed, then upscale
    th_max = 420
    th_sc = max(1, int(math.ceil(max(w_s, h_s) / th_max)))
    if th_sc > 1:
        tw, th = max(8, w_s // th_sc), max(8, h_s // th_sc)
        mask_s = np.asarray(
            Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
                (tw, th), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127
        face_s = np.asarray(
            Image.fromarray((mask_face.astype(np.uint8) * 255), mode="L").resize(
                (tw, th), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127
    else:
        mask_s, face_s = mask, mask_face
    skel_s = _zhang_suen_thin(mask_s, max_iter=14 if strength <= 2 else 10)
    skel_s = _spur_prune(skel_s, min_spur=6 if strength <= 1 else 5)
    if th_sc > 1:
        skel = np.asarray(
            Image.fromarray((skel_s.astype(np.uint8) * 255), mode="L").resize(
                (w_s, h_s), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127
    else:
        skel = skel_s
    from numpy.lib.stride_tricks import sliding_window_view as _swv

    skel_pad = np.pad(skel.astype(np.uint8), 1, mode="constant")
    skel_dil = _swv(skel_pad, (3, 3)).max(axis=(2, 3)).astype(bool)
    # Skeleton chains + residual face features not covered by skeleton
    trace_mask = skel | (mask_face & ~skel_dil)

    min_len = 16 if strength <= 1 else (14 if strength == 2 else 10)
    contours = _trace_edge_chains(trace_mask, min_len=min_len)

    # Dual-axis silhouette only (long strokes) — avoids hair noise piles
    dots1 = _getdots(mask_hi)
    c1 = _connectdots(dots1)
    pil = Image.fromarray(mask_hi.astype(np.uint8) * 255, mode="L")
    pil2 = pil.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    mask2 = np.asarray(pil2, dtype=np.uint8) > 127
    dots2 = _getdots(mask2)
    c2 = _connectdots(dots2)
    c2_mapped: list[list[tuple[int, int]]] = [[(p[1], p[0]) for p in c] for c in c2]
    sil_min = max(36, min_len * 3)
    for c in c1 + c2_mapped:
        if len(c) >= sil_min:
            contours.append([(float(x), float(y)) for x, y in c])

    contours = _merge_bidirectional(contours, dist_thresh=10.0 if strength <= 1 else 12.0)
    # Second pass with tighter gap after orientation settle
    contours = _merge_bidirectional(contours, dist_thresh=6.0 if strength <= 1 else 8.0)

    step = 2 if strength <= 2 else 3
    contours = _subsample(contours, step=step)
    scaled: list[list[tuple[float, float]]] = [[(x * sc, y * sc) for x, y in c] for c in contours]

    tol = 1.35 if strength <= 1 else (1.7 if strength == 2 else 2.2)
    scaled = _dp_simplify_px(scaled, tolerance=tol * float(sc))

    def plen(pts):
        t = 0.0
        for i in range(1, len(pts)):
            t += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        return t

    # Keep medium feature strokes; drop speckles
    min_px = 24.0 if strength <= 1 else (18.0 if strength == 2 else 12.0)
    scaled = [c for c in scaled if plen(c) >= min_px]

    def bbox_ok(pts):
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        return (max(xs)-min(xs) >= 4.0) or (max(ys)-min(ys) >= 4.0)

    scaled = [c for c in scaled if bbox_ok(c)]

    # Prefer paths that touch the face ROI (feature retention) when over budget
    if len(scaled) > max_paths:
        face_big = np.asarray(
            Image.fromarray((face_d.astype(np.uint8) * 255), mode="L").resize(
                (w0, h0), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127

        def face_score(pts):
            hits = 0
            for x, y in pts[:: max(1, len(pts) // 12)]:
                ix, iy = int(round(x)), int(round(y))
                if 0 <= iy < h0 and 0 <= ix < w0 and face_big[iy, ix]:
                    hits += 1
            return hits * 1000.0 + plen(pts)

        scaled.sort(key=face_score, reverse=True)
        scaled = scaled[:max_paths]
    else:
        scaled.sort(key=plen, reverse=True)

    amount = 2.0 * float(jitter)
    scaled = _apply_jitter(scaled, amount_px=amount, seed=seed)
    return scaled[:max_paths], edge_full



def _midtone_hatch_mask(small: np.ndarray) -> np.ndarray:
    """
    True where hatch is allowed: midtones with local structure.

    Skips flat near-black walls. Includes soft face midtones (cheeks)
    even when relatively bright after autocontrast.
    """
    arr = small.astype(np.float32)
    lo = float(np.percentile(arr, 12))
    hi = float(np.percentile(arr, 94))
    lo = max(26.0, min(lo, 80.0))
    hi = min(235.0, max(hi, 170.0))
    tone = (arr >= lo) & (arr <= hi)

    pad = np.pad(arr, 1, mode="edge")
    from numpy.lib.stride_tricks import sliding_window_view

    win = sliding_window_view(pad, (3, 3))
    local_std = win.reshape(win.shape[0], win.shape[1], -1).std(axis=2)
    # Softer gate on brighter cells (face skin); stricter on dark cells (walls)
    structured = np.where(arr >= 120.0, local_std >= 2.2, local_std >= 3.5)
    not_wall = ~((arr < 42.0) & (local_std < 7.0))
    return tone & structured & not_wall


def hatch_from_lum(
    lum: np.ndarray,
    *,
    hatch_size: int = 16,
    jitter: float = 0.04,
    seed: int = 1,
    max_paths: int = 4000,
) -> list[list[tuple[float, float]]]:
    """Portrait midtone hatch with long joined strokes. hatch_size<=0 → empty."""
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
    small = autocontrast_lum(small.astype(np.float32), cutoff=6.0)
    allow = _midtone_hatch_mask(small)

    lg1: list[list[tuple[float, float]]] = []
    lg2: list[list[tuple[float, float]]] = []
    hs = float(sc)
    vals = small.astype(np.float32)
    for y0 in range(h_s):
        for x0 in range(w_s):
            if not allow[y0, x0]:
                continue
            v = float(vals[y0, x0])
            x = x0 * hs
            y = y0 * hs + (0.15 * hs if (x0 % 2) else 0.0)
            # Long cell-spanning strokes (joinable) — avoids tiny + marks
            if v > 180:
                lg1.append([(x, y + hs * 0.4), (x + hs, y + hs * 0.4)])
            elif v > 120:
                lg1.append([(x, y + hs * 0.35), (x + hs, y + hs * 0.35)])
                if (x0 + y0) % 2 == 0:
                    lg2.append([(x + hs, y), (x, y + hs)])
            else:
                lg1.append([(x, y + hs * 0.25), (x + hs, y + hs * 0.25)])
                lg1.append([(x, y + hs * 0.65), (x + hs, y + hs * 0.65)])
                lg2.append([(x + hs, y), (x, y + hs)])

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

    lines = join_collinear(lg1) + join_collinear(lg2)
    # Drop tiny leftovers
    lines = [l for l in lines if math.hypot(l[-1][0] - l[0][0], l[-1][1] - l[0][1]) >= hs * 0.6]
    table = _make_perlin_table(seed)
    amount = float(sc) * float(jitter) * 0.2
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


def curve_tone_from_lum(
    lum: np.ndarray,
    *,
    cell: int = 14,
    jitter: float = 0.04,
    seed: int = 2,
    max_paths: int = 3000,
) -> list[list[tuple[float, float]]]:
    """
    ScribbleTrace-inspired intensity curves: denser wavy strokes in darker midtones.

    Skips flat dark walls via the same midtone mask as hatch. Output is px-space
    polylines suitable for polylines_to_mm.
    """
    sc = max(6, int(cell))
    h0, w0 = lum.shape
    w_s = max(4, w0 // sc)
    h_s = max(4, int(round(h0 * (w_s / w0))))
    small = np.asarray(
        Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L").resize(
            (w_s, h_s), Image.Resampling.LANCZOS
        ),
        dtype=np.uint8,
    )
    small = autocontrast_lum(small.astype(np.float32), cutoff=6.0)
    allow = _midtone_hatch_mask(small)
    vals = small.astype(np.float32)
    hs = float(sc)
    table = _make_perlin_table(seed)
    out: list[list[tuple[float, float]]] = []
    for y0 in range(h_s):
        for x0 in range(w_s):
            if not allow[y0, x0]:
                continue
            v = float(vals[y0, x0])
            # Darker → more / taller waves
            ink = 1.0 - (v / 255.0)
            if ink < 0.12:
                continue
            n_seg = 1 if ink < 0.35 else (2 if ink < 0.55 else 3)
            amp = hs * (0.12 + 0.35 * ink)
            period = max(3, int(6 - 3 * ink))
            x_base = x0 * hs
            y_base = y0 * hs + hs * 0.5
            for s in range(n_seg):
                pts: list[tuple[float, float]] = []
                y_off = (s - (n_seg - 1) / 2.0) * hs * 0.22
                for k in range(period + 1):
                    t = k / period
                    x = x_base + t * hs
                    wave = amp * math.sin(t * math.pi * (1.5 + ink))
                    jx = hs * jitter * (_perlin_noise(table, x0 * 0.2, y0 * 0.2 + s, k * 0.3) - 0.5)
                    jy = hs * jitter * (_perlin_noise(table, x0 * 0.2, y0 * 0.2 + s, k * 0.3 + 3) - 0.5)
                    pts.append((x + jx, y_base + y_off + wave + jy))
                if len(pts) >= 2:
                    out.append(pts)
                if len(out) >= max_paths:
                    return out
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


def _path_length_px(pts: list[tuple[float, float]]) -> float:
    t = 0.0
    for i in range(1, len(pts)):
        t += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    return t


def face_roi_mask(lum: np.ndarray) -> np.ndarray:
    """
    Bright central subject mask (face/torso) for budget + island kill.

    Uses autocontrasted luma + central prior so dark walls stay outside.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    h, w = lum.shape
    u8 = autocontrast_lum(np.asarray(lum, dtype=np.float32), cutoff=6.0).astype(np.float32)
    bright = u8 >= 95.0
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = h * 0.42, w * 0.5
    # Elliptical prior covering head + shoulders
    prior = (((yy - cy) / max(h * 0.42, 1.0)) ** 2 + ((xx - cx) / max(w * 0.38, 1.0)) ** 2) <= 1.0
    mask = bright & prior
    if int(mask.sum()) < max(64, (h * w) // 40):
        mask = prior & (u8 >= 70.0)
    pad = np.pad(mask.astype(np.uint8), 3, mode="constant")
    return sliding_window_view(pad, (7, 7)).max(axis=(2, 3)).astype(bool)


def _path_face_fraction(
    pts: list[tuple[float, float]],
    face: np.ndarray,
) -> float:
    h, w = face.shape
    if len(pts) < 2:
        return 0.0
    step = max(1, len(pts) // 16)
    hits = 0
    n = 0
    for x, y in pts[::step]:
        ix, iy = int(round(x)), int(round(y))
        n += 1
        if 0 <= iy < h and 0 <= ix < w and face[iy, ix]:
            hits += 1
    return hits / max(1, n)


def prune_edge_islands(
    contours: list[list[tuple[float, float]]],
    face: np.ndarray,
    *,
    outside_min_len: float = 52.0,
    inside_min_len: float = 14.0,
) -> list[list[tuple[float, float]]]:
    """Drop short peripheral islands; keep structure inside face ROI."""
    out: list[list[tuple[float, float]]] = []
    for c in contours:
        if len(c) < 2:
            continue
        plen = _path_length_px(c)
        frac = _path_face_fraction(c, face)
        if frac >= 0.35:
            if plen >= inside_min_len:
                out.append(c)
        elif plen >= outside_min_len:
            out.append(c)
    return out


def allocate_face_budget(
    contours: list[list[tuple[float, float]]],
    face: np.ndarray,
    max_paths: int,
    *,
    face_fraction: float = 0.78,
) -> list[list[tuple[float, float]]]:
    """Spend most of the edge budget on face-touching strokes."""
    max_paths = max(1, int(max_paths))
    face_cap = max(1, int(round(max_paths * float(face_fraction))))
    outside_cap = max(0, max_paths - face_cap)

    scored_in: list[tuple[float, list[tuple[float, float]]]] = []
    scored_out: list[tuple[float, list[tuple[float, float]]]] = []
    for c in contours:
        if len(c) < 2:
            continue
        plen = _path_length_px(c)
        frac = _path_face_fraction(c, face)
        score = plen + frac * 80.0
        if frac >= 0.35:
            scored_in.append((score, c))
        else:
            scored_out.append((score, c))
    scored_in.sort(key=lambda t: t[0], reverse=True)
    scored_out.sort(key=lambda t: t[0], reverse=True)
    picked = [c for _, c in scored_in[:face_cap]]
    # Unused face slots can absorb long outside structure
    slack = max(0, face_cap - len(picked)) + outside_cap
    picked.extend(c for _, c in scored_out[:slack])
    return picked[:max_paths]


def repair_arc_gaps(
    contours: list[list[tuple[float, float]]],
    lum: np.ndarray,
    face: np.ndarray,
    *,
    min_gap: float = 6.0,
    max_gap: float = 22.0,
) -> list[list[tuple[float, float]]]:
    """
    Splice nearby stroke ends that continue a dark facial arc (glasses/jaw).

    Bridges only inside the face ROI when the midpoint sits on a darker ridge.
    """
    if len(contours) < 2:
        return contours
    h, w = lum.shape
    u8 = autocontrast_lum(np.asarray(lum, dtype=np.float32), cutoff=6.0).astype(np.float32)
    alive: list[list[tuple[float, float]] | None] = [list(c) for c in contours if len(c) > 1]

    def end_dir(pts: list[tuple[float, float]], at_end: bool) -> tuple[float, float]:
        if len(pts) < 2:
            return (1.0, 0.0)
        if at_end:
            x0, y0 = pts[-2]
            x1, y1 = pts[-1]
        else:
            x0, y0 = pts[1]
            x1, y1 = pts[0]
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1.0
        return (dx / n, dy / n)

    def dark_mid(x: float, y: float) -> bool:
        ix, iy = int(round(x)), int(round(y))
        if not (1 <= iy < h - 1 and 1 <= ix < w - 1):
            return False
        if not face[iy, ix]:
            return False
        # Prefer darker-than-local-mean ridges (frames / jaw)
        patch = u8[iy - 1 : iy + 2, ix - 1 : ix + 2]
        return float(u8[iy, ix]) <= float(patch.mean()) + 8.0 and float(u8[iy, ix]) < 150.0

    for _ in range(min(48, len(alive) * 2)):
        best = None  # (score, i, j, rev_i, rev_j, mx, my)
        n = len(alive)
        for i in range(n):
            if alive[i] is None:
                continue
            a = alive[i]
            assert a is not None
            for j in range(i + 1, n):
                if alive[j] is None:
                    continue
                b = alive[j]
                assert b is not None
                # Try joining end(a)→start(b) under four orientations
                configs = (
                    (False, False, a[-1], b[0], end_dir(a, True), end_dir(b, False)),
                    (False, True, a[-1], b[-1], end_dir(a, True), end_dir(list(reversed(b)), False)),
                    (True, False, a[0], b[0], end_dir(list(reversed(a)), True), end_dir(b, False)),
                    (True, True, a[0], b[-1], end_dir(list(reversed(a)), True), end_dir(list(reversed(b)), False)),
                )
                for rev_i, rev_j, p, q, da, db in configs:
                    dist = math.hypot(p[0] - q[0], p[1] - q[1])
                    if dist < min_gap or dist > max_gap:
                        continue
                    # Continuity: leaving a should point roughly toward arriving into b
                    vx, vy = (q[0] - p[0]) / dist, (q[1] - p[1]) / dist
                    align = da[0] * vx + da[1] * vy
                    align_b = -(db[0] * vx + db[1] * vy)
                    if align < 0.35 or align_b < 0.15:
                        continue
                    mx, my = (p[0] + q[0]) * 0.5, (p[1] + q[1]) * 0.5
                    if not dark_mid(mx, my):
                        continue
                    score = align + align_b - dist * 0.02
                    if best is None or score > best[0]:
                        best = (score, i, j, rev_i, rev_j, mx, my)
        if best is None:
            break
        _, i, j, rev_i, rev_j, mx, my = best
        a = alive[i]
        b = alive[j]
        assert a is not None and b is not None
        aa = list(reversed(a)) if rev_i else list(a)
        bb = list(reversed(b)) if rev_j else list(b)
        bridge = [aa[-1], (mx, my), bb[0]]
        alive[i] = aa + bridge[1:] + bb[1:]
        alive[j] = None

    return [c for c in alive if c is not None and len(c) > 1]


def refine_edge_polylines(
    contours: list[list[tuple[float, float]]],
    lum: np.ndarray,
    *,
    max_paths: int,
) -> list[list[tuple[float, float]]]:
    """Island kill + arc splice + face-weighted budget (final edge pass)."""
    face = face_roi_mask(lum)
    cleaned = prune_edge_islands(contours, face)
    cleaned = repair_arc_gaps(cleaned, lum, face)
    cleaned = _merge_bidirectional(cleaned, dist_thresh=8.0)
    return allocate_face_budget(cleaned, face, max_paths)


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
    # Over-extract then refine so face budget can choose
    raw_budget = min(max_edge_paths * 2, max(max_edge_paths + 80, 400))
    contours_px, edge_map = contours_from_lum(
        lum_u8,
        simplify=contour_simplify,
        jitter=jitter,
        seed=seed,
        max_paths=raw_budget,
    )
    contours_px = refine_edge_polylines(contours_px, lum_u8, max_paths=max_edge_paths)
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


def edge_polylines_from_lum(
    lum: np.ndarray,
    *,
    contour_simplify: int = 2,
    jitter: float = 0.04,
    seed: int = 0,
    max_paths: int = 2000,
) -> tuple[list[list[tuple[float, float]]], np.ndarray]:
    """Edges only in pixel space (ensemble variant pass)."""
    lum_u8 = autocontrast_lum(np.asarray(lum, dtype=np.float32), cutoff=10.0).astype(np.float32)
    return contours_from_lum(
        lum_u8,
        simplify=contour_simplify,
        jitter=jitter,
        seed=seed,
        max_paths=max_paths,
    )


def polylines_to_ink_map(
    polylines_px: list[list[tuple[float, float]]],
    *,
    height: int,
    width: int,
    stroke_radius: int = 1,
) -> np.ndarray:
    """Rasterize polylines into a float ink accumulator (pixel coords)."""
    from PIL import ImageDraw

    h, w = int(height), int(width)
    canvas = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(canvas)
    width_px = max(1, int(stroke_radius) * 2 + 1)
    for pts in polylines_px:
        if len(pts) < 2:
            continue
        xy = [(float(x), float(y)) for x, y in pts]
        draw.line(xy, fill=255, width=width_px)
    return (np.asarray(canvas, dtype=np.float32) / 255.0).astype(np.float32)


def consensus_from_ink_maps(
    ink_maps: Sequence[np.ndarray],
    *,
    core_votes: int = 2,
    fill_votes: int = 1,
) -> np.ndarray:
    """
    Vote across variant ink maps.

    Pixels seen in ≥ core_votes variants form the core skeleton ink.
    Fill candidates (≥ fill_votes) are kept when they bridge into the core
    (geodesic grow) so complementary gap edges survive without free noise.
    """
    if not ink_maps:
        return np.zeros((8, 8), dtype=bool)
    stack = np.stack([(m > 0.15).astype(np.uint8) for m in ink_maps], axis=0)
    votes = stack.sum(axis=0)
    core = votes >= int(core_votes)
    fill = votes >= int(fill_votes)
    strong = votes >= max(int(core_votes), 2)
    from numpy.lib.stride_tricks import sliding_window_view

    grown = (core | strong).astype(bool)
    fill_pool = fill.astype(bool)
    for _ in range(24):
        pad = np.pad(grown.astype(np.uint8), 1, mode="constant")
        dil = sliding_window_view(pad, (3, 3)).max(axis=(2, 3)).astype(bool)
        nxt = grown | (dil & fill_pool)
        if int(nxt.sum()) == int(grown.sum()):
            break
        grown = nxt
    return grown.astype(bool)


def contours_from_edge_mask(
    mask: np.ndarray,
    *,
    simplify: int = 2,
    jitter: float = 0.04,
    seed: int = 0,
    max_paths: int = 2000,
) -> list[list[tuple[float, float]]]:
    """
    Sixth-pass vectorize: skeleton + chain walk on a consensus edge mask.

    Does not re-run photo edge detection — traces the voted ink map only.
    """
    h0, w0 = mask.shape
    strength = max(1, int(simplify))
    sc = 2 if strength >= 3 else 1
    w_s = max(8, w0 // sc)
    h_s = max(8, int(round(h0 * (w_s / w0))))
    mask_s0 = np.asarray(
        Image.fromarray((np.asarray(mask, dtype=bool).astype(np.uint8) * 255), mode="L").resize(
            (w_s, h_s), Image.Resampling.NEAREST
        ),
        dtype=np.uint8,
    ) > 127

    th_max = 420
    th_sc = max(1, int(math.ceil(max(w_s, h_s) / th_max)))
    if th_sc > 1:
        tw, th = max(8, w_s // th_sc), max(8, h_s // th_sc)
        mask_thin = np.asarray(
            Image.fromarray((mask_s0.astype(np.uint8) * 255), mode="L").resize(
                (tw, th), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127
    else:
        mask_thin = mask_s0

    skel_s = _zhang_suen_thin(mask_thin, max_iter=14 if strength <= 2 else 10)
    skel_s = _spur_prune(skel_s, min_spur=5 if strength <= 1 else 4)
    if th_sc > 1:
        skel = np.asarray(
            Image.fromarray((skel_s.astype(np.uint8) * 255), mode="L").resize(
                (w_s, h_s), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        ) > 127
    else:
        skel = skel_s

    # Residual ink not covered by skeleton (gap fillers)
    from numpy.lib.stride_tricks import sliding_window_view as _swv

    skel_pad = np.pad(skel.astype(np.uint8), 1, mode="constant")
    skel_dil = _swv(skel_pad, (3, 3)).max(axis=(2, 3)).astype(bool)
    trace_mask = skel | (mask_s0 & ~skel_dil)

    min_len = 14 if strength <= 1 else (12 if strength == 2 else 8)
    contours = _trace_edge_chains(trace_mask, min_len=min_len)

    # Long dual-axis strokes from consensus mask (structure)
    dots1 = _getdots(mask_s0)
    c1 = _connectdots(dots1)
    pil = Image.fromarray(mask_s0.astype(np.uint8) * 255, mode="L")
    pil2 = pil.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    mask2 = np.asarray(pil2, dtype=np.uint8) > 127
    dots2 = _getdots(mask2)
    c2 = _connectdots(dots2)
    c2_mapped: list[list[tuple[int, int]]] = [[(p[1], p[0]) for p in c] for c in c2]
    sil_min = max(28, min_len * 2)
    for c in c1 + c2_mapped:
        if len(c) >= sil_min:
            contours.append([(float(x), float(y)) for x, y in c])

    contours = _merge_bidirectional(contours, dist_thresh=10.0 if strength <= 1 else 12.0)
    contours = _merge_bidirectional(contours, dist_thresh=6.0 if strength <= 1 else 8.0)

    step = 2 if strength <= 2 else 3
    contours = _subsample(contours, step=step)
    scaled: list[list[tuple[float, float]]] = [[(x * sc, y * sc) for x, y in c] for c in contours]
    tol = 1.2 if strength <= 1 else (1.55 if strength == 2 else 2.0)
    scaled = _dp_simplify_px(scaled, tolerance=tol * float(sc))

    def plen(pts):
        t = 0.0
        for i in range(1, len(pts)):
            t += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        return t

    min_px = 20.0 if strength <= 1 else (16.0 if strength == 2 else 10.0)
    scaled = [c for c in scaled if plen(c) >= min_px]
    scaled.sort(key=plen, reverse=True)
    scaled = scaled[:max_paths]
    amount = 2.0 * float(jitter)
    scaled = _apply_jitter(scaled, amount_px=amount, seed=seed)
    return scaled[:max_paths]
