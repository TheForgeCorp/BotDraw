"""Portrait ingest: preprocess + edges + vtracer regions → PortraitVector."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from shapely.geometry import LineString

from botdraw.core.models import PAPER_MM, PaperSize, QualityPreset, QUALITY_LIMITS
from botdraw.portrait.frame import apply_crop_pil, auto_frame_rgb, normalize_crop
from botdraw.portrait.models import ColorCluster, CropRect, PortraitVector, RegionPoly
from botdraw.styles.image_utils import luminance, map_to_page, synthetic_portrait


_PATH_CMD = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
)
_TRANSLATE_RE = re.compile(
    r"translate\(\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*[,\s]\s*"
    r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*\)",
    re.I,
)
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


def default_posterize_levels(quality: QualityPreset) -> int:
    if quality == QualityPreset.BOOTH_FAST:
        return 4
    if quality == QualityPreset.STUDIO_HQ:
        return 8
    return 6


def default_filter_speckle(quality: QualityPreset) -> int:
    if quality == QualityPreset.BOOTH_FAST:
        return 12
    if quality == QualityPreset.STUDIO_HQ:
        return 4
    return 8


def default_min_path_points(quality: QualityPreset) -> int:
    if quality == QualityPreset.BOOTH_FAST:
        return 8
    if quality == QualityPreset.STUDIO_HQ:
        return 5
    return 6


def _posterize_rgb(rgb: np.ndarray, levels: int) -> np.ndarray:
    """Quantize each channel to `levels` steps (0 = off). SVGcode-inspired."""
    n = int(levels)
    if n <= 0:
        return rgb
    n = max(2, min(32, n))
    step = 255.0 / (n - 1)
    return np.clip(np.round(np.asarray(rgb, dtype=np.float32) / step) * step, 0, 255)


def _contrast_boost(rgb: np.ndarray, amount: float) -> np.ndarray:
    if amount is None or abs(float(amount) - 1.0) < 1e-3:
        return rgb
    a = float(amount)
    mid = 128.0
    return np.clip((np.asarray(rgb, dtype=np.float32) - mid) * a + mid, 0, 255)


def _parse_hex_rgb(fill: str | None) -> tuple[float, float, float] | None:
    if not fill:
        return None
    m = _HEX_RE.match(fill.strip())
    if not m:
        return None
    h = m.group(1)
    return (float(int(h[0:2], 16)), float(int(h[2:4], 16)), float(int(h[4:6], 16)))


def _cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 6,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        out.append((float(x), float(y)))
    return out


def _parse_svg_paths(svg_text: str) -> list[tuple[list[tuple[float, float]], str | None]]:
    """
    Extract polylines from vtracer SVG.

    VTracer emits path `d` in local coords plus transform=\"translate(tx,ty)\".
    Ignoring translate produced page-frame boxes and long travel diagonals.
    """
    root = ET.fromstring(svg_text)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    out: list[tuple[list[tuple[float, float]], str | None]] = []
    for el in root.iter(f"{ns}path"):
        d = el.attrib.get("d") or ""
        fill = el.attrib.get("fill")
        tx, ty = 0.0, 0.0
        tr = el.attrib.get("transform") or ""
        m = _TRANSLATE_RE.search(tr)
        if m:
            tx, ty = float(m.group(1)), float(m.group(2))

        pts: list[tuple[float, float]] = []
        nums: list[float] = []
        cmd = "M"
        flat: list[str] = []
        for a, b in _PATH_CMD.findall(d):
            flat.append(a or b)
        i = 0
        cx, cy = 0.0, 0.0
        while i < len(flat):
            t = flat[i]
            if re.match(r"^[A-Za-z]$", t):
                cmd = t
                i += 1
                continue
            try:
                nums.append(float(t))
            except ValueError:
                pass
            i += 1

            def _take(n: int) -> list[float] | None:
                nonlocal nums
                if len(nums) < n:
                    return None
                chunk, nums = nums[:n], nums[n:]
                return chunk

            if cmd in ("M", "L", "m", "l"):
                chunk = _take(2)
                if not chunk:
                    continue
                x, y = chunk
                if cmd in ("m", "l"):
                    x += cx
                    y += cy
                cx, cy = x, y
                pts.append((x + tx, y + ty))
                if cmd == "M":
                    cmd = "L"
                elif cmd == "m":
                    cmd = "l"
            elif cmd in ("H", "h"):
                chunk = _take(1)
                if not chunk:
                    continue
                x = chunk[0] + (cx if cmd == "h" else 0.0)
                y = cy
                cx = x
                pts.append((x + tx, y + ty))
            elif cmd in ("V", "v"):
                chunk = _take(1)
                if not chunk:
                    continue
                y = chunk[0] + (cy if cmd == "v" else 0.0)
                x = cx
                cy = y
                pts.append((x + tx, y + ty))
            elif cmd in ("C", "c"):
                chunk = _take(6)
                if not chunk:
                    continue
                x1, y1, x2, y2, x, y = chunk
                if cmd == "c":
                    x1, y1 = x1 + cx, y1 + cy
                    x2, y2 = x2 + cx, y2 + cy
                    x, y = x + cx, y + cy
                p0 = (cx, cy)
                for px, py in _cubic(p0, (x1, y1), (x2, y2), (x, y)):
                    pts.append((px + tx, py + ty))
                cx, cy = x, y
            elif cmd in ("Z", "z"):
                if pts:
                    # close in local space already translated
                    first = pts[0]
                    if abs(first[0] - (cx + tx)) > 1e-3 or abs(first[1] - (cy + ty)) > 1e-3:
                        pts.append(first)
                    cx, cy = first[0] - tx, first[1] - ty
                nums.clear()
        if len(pts) >= 3:
            out.append((pts, fill))
    return out


def _poly_area(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 3:
        return 0.0
    x = np.array([p[0] for p in pts], dtype=np.float64)
    y = np.array([p[1] for p in pts], dtype=np.float64)
    return float(abs(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))) if len(pts) > 1 else 0.0


def _mean_rgb_in_poly(rgb: np.ndarray, pts_px: list[tuple[float, float]]) -> tuple[float, float, float]:
    h, w = rgb.shape[:2]
    xs = [p[0] for p in pts_px]
    ys = [p[1] for p in pts_px]
    x0, x1 = max(0, int(min(xs))), min(w, int(max(xs)) + 1)
    y0, y1 = max(0, int(min(ys))), min(h, int(max(ys)) + 1)
    if x1 <= x0 or y1 <= y0:
        return (128.0, 128.0, 128.0)
    patch = rgb[y0:y1, x0:x1]
    return (
        float(patch[..., 0].mean()),
        float(patch[..., 1].mean()),
        float(patch[..., 2].mean()),
    )


def _polyline_length(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(pts)):
        total += float(np.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    return total


def _split_on_jumps(
    pts: list[tuple[float, float]],
    max_jump: float,
) -> list[list[tuple[float, float]]]:
    """Break polylines at absurd gaps (travel artifacts)."""
    if len(pts) < 2:
        return []
    chunks: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = [pts[0]]
    for i in range(1, len(pts)):
        d = float(np.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
        if d > max_jump and len(cur) >= 2:
            chunks.append(cur)
            cur = [pts[i]]
        else:
            cur.append(pts[i])
    if len(cur) >= 2:
        chunks.append(cur)
    return chunks


def _trace_contour_from(
    mask: np.ndarray,
    visited: np.ndarray,
    start: tuple[int, int],
) -> list[tuple[float, float]]:
    """Moore-neighborhood boundary walk starting at an on-pixel."""
    h, w = mask.shape
    deltas = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    y, x = start
    pts: list[tuple[float, float]] = [(float(x), float(y))]
    visited[y, x] = True
    back_dir = 6
    for _ in range(h * w * 2):
        found = None
        for k in range(8):
            d = (back_dir + 6 + k) % 8
            ny, nx = y + deltas[d][0], x + deltas[d][1]
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx]:
                found = (ny, nx, d)
                break
        if found is None:
            break
        y, x, d = found
        pts.append((float(x), float(y)))
        visited[y, x] = True
        back_dir = d
        if (y, x) == start and len(pts) > 3:
            break
        if len(pts) > max(h, w) * 8:
            break
    return pts


def _is_page_frame_polyline(
    pts: list[tuple[float, float]],
    page_w: float,
    page_h: float,
) -> bool:
    """True if polyline is essentially the paper/image border rectangle."""
    if len(pts) < 4:
        return False
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bw = max(xs) - min(xs)
    bh = max(ys) - min(ys)
    return bw >= 0.82 * page_w and bh >= 0.82 * page_h


def _edge_polylines(
    edge_map: np.ndarray,
    *,
    step: int,
    max_paths: int,
    page_w: float,
    page_h: float,
    min_path_points: int = 6,
    min_length_px: float = 10.0,
) -> list[list[tuple[float, float]]]:
    """
    Connected edge contours from edge_map (not horizontal-only runs).

    Threshold → binary → Moore boundary traces → jump-split → simplify → budget.
    """
    h, w = edge_map.shape
    thr = max(28.0, float(np.percentile(edge_map, 90)))
    mask = edge_map >= thr
    # Ignore image-border pixels (common FIND_EDGES frame artifact)
    margin = 2
    mask[:margin, :] = False
    mask[-margin:, :] = False
    mask[:, :margin] = False
    mask[:, -margin:] = False
    # Despeckle: keep pixels with at least 2 on-neighbors
    padded = np.pad(mask.astype(np.uint8), 1, mode="constant")
    neigh = np.zeros((h, w), dtype=np.int16)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            neigh += padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    mask = mask & (neigh >= 2)

    # Prefer true boundary pixels
    boundary = np.zeros_like(mask, dtype=bool)
    padded2 = np.pad(mask.astype(np.uint8), 1, mode="constant")
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            neighbor = padded2[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w].astype(bool)
            boundary |= mask & (~neighbor)
    if not np.any(boundary):
        boundary = mask

    visited = np.zeros_like(boundary, dtype=bool)
    seeds: list[tuple[int, int]] = []
    for y in range(0, h, max(1, step)):
        row = boundary[y]
        for x in range(0, w, max(1, step)):
            if row[x] and not visited[y, x]:
                seeds.append((y, x))

    scored: list[tuple[float, list[tuple[float, float]]]] = []
    max_jump_px = max(6.0, min(w, h) * 0.04)
    for sy, sx in seeds:
        if visited[sy, sx] or not boundary[sy, sx]:
            continue
        pts_px = _trace_contour_from(boundary, visited, (sy, sx))
        for chunk in _split_on_jumps(pts_px, max_jump_px):
            if len(chunk) < max(4, int(min_path_points)):
                continue
            ink_vals = []
            for x, y in chunk:
                ix, iy = int(np.clip(x, 0, w - 1)), int(np.clip(y, 0, h - 1))
                ink_vals.append(float(edge_map[iy, ix]))
            mean_ink = float(np.mean(ink_vals)) if ink_vals else 0.0
            length = _polyline_length(chunk)
            if length < float(min_length_px):
                continue
            scored.append((length * (0.25 + mean_ink / 255.0), chunk))

    scored.sort(key=lambda t: -t[0])
    out: list[list[tuple[float, float]]] = []
    max_jump_mm = max(4.0, min(page_w, page_h) * 0.05)
    for _, pts_px in scored[: max_paths * 2]:
        mm = [map_to_page(x, y, img_w=w, img_h=h, page_w=page_w, page_h=page_h) for x, y in pts_px]
        for piece in _split_on_jumps(mm, max_jump_mm):
            if len(piece) < max(2, int(min_path_points) // 2):
                continue
            if _is_page_frame_polyline(piece, page_w, page_h):
                continue
            try:
                simple = list(LineString(piece).simplify(0.45, preserve_topology=False).coords)
                cleaned = [(float(a), float(b)) for a, b in simple]
                if len(cleaned) >= 2 and _polyline_length(cleaned) >= 1.5:
                    if _is_page_frame_polyline(cleaned, page_w, page_h):
                        continue
                    out.append(cleaned)
            except Exception:
                if len(piece) >= 2:
                    out.append(piece)
        if len(out) >= max_paths:
            break
    return out[:max_paths]


def _vtracer_regions(
    rgb: np.ndarray,
    *,
    mode: str,
    quality: QualityPreset,
    page_w: float,
    page_h: float,
    max_regions: int,
    filter_speckle: int | None = None,
    min_path_points: int = 6,
    min_area_px: float = 64.0,
) -> list[RegionPoly]:
    h, w = rgb.shape[:2]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    try:
        import vtracer
    except ImportError:
        return []

    binary = mode in ("drawing", "lineart") or quality == QualityPreset.BOOTH_FAST
    speckle = int(filter_speckle) if filter_speckle is not None else default_filter_speckle(quality)
    layer_diff = 40 if quality == QualityPreset.BOOTH_FAST else (28 if quality == QualityPreset.BOOTH_BALANCED else 16)

    with TemporaryDirectory() as td:
        inp = Path(td) / "in.png"
        outp = Path(td) / "out.svg"
        img.save(inp)
        kwargs: dict[str, Any] = {
            "colormode": "binary" if binary else "color",
            "mode": "polygon",
            "filter_speckle": max(0, speckle),
            "corner_threshold": 60,
            "path_precision": 2,
        }
        if not binary:
            kwargs["hierarchical"] = "stacked"
            kwargs["layer_difference"] = layer_diff
            kwargs["color_precision"] = 5 if quality != QualityPreset.STUDIO_HQ else 7
        try:
            vtracer.convert_image_to_svg_py(str(inp), str(outp), **kwargs)
            svg = outp.read_text(encoding="utf-8")
        except Exception:
            return []

    paths = _parse_svg_paths(svg)
    img_area = float(w * h)
    max_jump_px = max(8.0, min(w, h) * 0.06)
    scored: list[tuple[float, list[tuple[float, float]], tuple[float, float, float]]] = []
    for pts, fill in paths:
        # Drop full-frame / near-full background shells (common vtracer first path)
        area = _poly_area(pts)
        if area < float(min_area_px):
            continue
        if area >= 0.82 * img_area:
            continue
        # Reject paths that still contain huge jumps after transform fix
        clean_chunks = _split_on_jumps(pts, max_jump_px)
        if not clean_chunks:
            continue
        # Prefer the largest contiguous chunk for closed regions
        pts_clean = max(clean_chunks, key=lambda c: _poly_area(c) if len(c) >= 3 else _polyline_length(c))
        if len(pts_clean) < max(3, int(min_path_points)):
            continue
        area = _poly_area(pts_clean)
        if area < float(min_area_px):
            continue
        if area >= 0.82 * img_area:
            continue
        mean = _parse_hex_rgb(fill) or _mean_rgb_in_poly(rgb, pts_clean)
        scored.append((area, pts_clean, mean))

    scored.sort(key=lambda t: -t[0])
    regions: list[RegionPoly] = []
    for i, (area, pts_px, mean) in enumerate(scored[:max_regions]):
        pts_mm = [
            map_to_page(x, y, img_w=w, img_h=h, page_w=page_w, page_h=page_h) for x, y in pts_px
        ]
        try:
            if len(pts_mm) >= 3:
                pts_mm = [(float(a), float(b)) for a, b in LineString(pts_mm).simplify(0.35).coords]
        except Exception:
            pass
        if len(pts_mm) < 3:
            continue
        regions.append(
            RegionPoly(
                id=f"r{i}",
                points_mm=pts_mm,
                mean_rgb=mean,
                area=float(area),
            )
        )
    return regions


def _preprocess_array(
    rgb: np.ndarray,
    mode: str,
    *,
    posterize_levels: int = 0,
    contrast: float = 1.0,
) -> np.ndarray:
    """Apply image_mode transforms, optional contrast + posterize."""
    m = (mode or "photo").lower()
    out = np.asarray(rgb, dtype=np.float32)
    if m != "photo":
        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")
        if m == "sketch":
            g = ImageOps.autocontrast(ImageOps.grayscale(img))
            img = Image.merge("RGB", (g, g, g))
        elif m == "lineart":
            g = ImageOps.grayscale(img)
            edges = ImageOps.invert(ImageOps.autocontrast(g.filter(ImageFilter.FIND_EDGES)))
            img = Image.merge("RGB", (edges, edges, edges))
        elif m == "drawing":
            g = ImageOps.grayscale(img)
            bw = g.point(lambda x: 255 if x > 160 else 0)
            img = Image.merge("RGB", (bw, bw, bw))
        out = np.asarray(img, dtype=np.float32)
    out = _contrast_boost(out, contrast)
    out = _posterize_rgb(out, posterize_levels)
    return out


def _resolve_ensemble(
    ensemble: bool | None,
    *,
    quality: QualityPreset,
    mode: str,
) -> bool:
    """Booth never ensembles; studio-hq photo auto-on; explicit flag otherwise."""
    if quality in (QualityPreset.BOOTH_FAST, QualityPreset.BOOTH_BALANCED):
        return False
    if ensemble is None:
        return (mode or "photo").lower() == "photo"
    return bool(ensemble)


def ingest_portrait(
    image_path: str | Path | None = None,
    *,
    image_array: np.ndarray | None = None,
    mode: str = "photo",
    quality: QualityPreset | str = QualityPreset.BOOTH_BALANCED,
    paper: PaperSize | str = PaperSize.A4,
    crop: CropRect | dict | None = None,
    auto_frame: bool = True,
    posterize_levels: int | None = None,
    filter_speckle: int | None = None,
    min_path_points: int | None = None,
    contrast: float = 1.12,
    contour_simplify: int | None = None,
    hatch_size: int | None = None,
    linedraw_jitter: float | None = None,
    ensemble: bool | None = None,
    scan_mode: str | None = None,
) -> PortraitVector:
    """Load/crop/preprocess image and build PortraitVector (tone + edges + regions)."""
    from botdraw.portrait.linedraw_edges import (
        autocontrast_lum,
        consensus_from_ink_maps,
        contours_from_edge_mask,
        edge_polylines_from_lum,
        hatch_from_lum,
        linedraw_edges_and_hatch,
        polylines_to_ink_map,
        polylines_to_mm,
        refine_edge_polylines,
    )
    from botdraw.portrait.scan_modes import normalize_scan_mode, scan_mode_knobs
    from botdraw.portrait.tone_grid import build_tone_grid, strokes_from_tone_grid
    from botdraw.portrait.tone_variants import ENSEMBLE_RECIPES, ToneRecipe, apply_tone_recipe

    t0 = time.perf_counter()
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
    paper_enum = paper if isinstance(paper, PaperSize) else PaperSize(paper)
    limits = QUALITY_LIMITS[quality_enum]
    max_side = int(limits["image_max"])
    max_paths = int(limits["max_paths"])
    page_w, page_h = PAPER_MM[paper_enum]
    use_ensemble = _resolve_ensemble(ensemble, quality=quality_enum, mode=mode or "photo")
    scan = normalize_scan_mode(scan_mode)
    sknobs = scan_mode_knobs(scan)

    post_n = default_posterize_levels(quality_enum) if posterize_levels is None else int(posterize_levels)
    speckle = default_filter_speckle(quality_enum) if filter_speckle is None else int(filter_speckle)
    min_pts = default_min_path_points(quality_enum) if min_path_points is None else int(min_path_points)
    # Linedraw defaults by quality
    if contour_simplify is None:
        csimp = 3 if quality_enum == QualityPreset.BOOTH_FAST else (2 if quality_enum == QualityPreset.BOOTH_BALANCED else 1)
    else:
        csimp = max(1, int(contour_simplify))
    if hatch_size is None:
        # Larger cells = fewer cleaner strokes; quality drives density
        hsize = 20 if quality_enum == QualityPreset.BOOTH_FAST else (14 if quality_enum == QualityPreset.BOOTH_BALANCED else 10)
    else:
        hsize = int(hatch_size)
    jitter = 0.02 if linedraw_jitter is None else float(linedraw_jitter)

    # Load full-res for framing
    if image_array is not None:
        full = np.asarray(image_array, dtype=np.float32)
        if full.ndim == 2:
            full = np.stack([full, full, full], axis=-1)
        img = Image.fromarray(np.clip(full, 0, 255).astype(np.uint8), mode="RGB")
    elif image_path:
        img = Image.open(image_path).convert("RGB")
        full = np.asarray(img, dtype=np.float32)
    else:
        full = synthetic_portrait(max_side)
        img = Image.fromarray(np.clip(full, 0, 255).astype(np.uint8), mode="RGB")

    # Resolve crop
    if crop is not None:
        crop_r = normalize_crop(crop)
    elif auto_frame:
        crop_r = auto_frame_rgb(full)
    else:
        crop_r = CropRect(source="full")

    img = apply_crop_pil(img, crop_r)
    # Resize to quality max_side
    w0, h0 = img.size
    scale = max_side / max(w0, h0)
    if scale < 1:
        img = img.resize((max(1, int(w0 * scale)), max(1, int(h0 * scale))), Image.Resampling.LANCZOS)

    rgb_cropped = np.asarray(img, dtype=np.float32)

    ensemble_meta: dict[str, Any] = {"enabled": False}
    t_variants = 0.0
    if use_ensemble:
        # Mode transforms only; each recipe owns contrast/hue/sat/shadow
        rgb_mode = _preprocess_array(rgb_cropped, mode, posterize_levels=0, contrast=1.0)
        recipes: list[ToneRecipe] = list(ENSEMBLE_RECIPES)
        if abs(float(contrast) - 1.12) > 1e-3:
            recipes[0] = ToneRecipe(id="base", contrast=float(contrast))
        rgb = _posterize_rgb(apply_tone_recipe(rgb_mode, recipes[0]), post_n)
    else:
        rgb_mode = None
        recipes = []
        rgb = _preprocess_array(rgb_cropped, mode, posterize_levels=post_n, contrast=float(contrast))
    t_pre = time.perf_counter()
    t_variants = t_pre

    lum = luminance(rgb)
    ink_target = np.clip(1.0 - lum / 255.0, 0.0, 1.0).astype(np.float32)

    edge_budget = min(
        max_paths // 2,
        350 if quality_enum == QualityPreset.BOOTH_FAST else (900 if quality_enum == QualityPreset.BOOTH_BALANCED else 1100),
    )
    hatch_budget = min(
        max_paths,
        800 if quality_enum == QualityPreset.BOOTH_FAST else (2000 if quality_enum == QualityPreset.BOOTH_BALANCED else 3500),
    )

    if use_ensemble:
        assert rgb_mode is not None
        h_px, w_px = rgb.shape[:2]
        ink_maps: list[np.ndarray] = []
        recipe_ids: list[str] = []
        variant_edge_counts: list[int] = []
        for i, recipe in enumerate(recipes):
            var_rgb = _posterize_rgb(apply_tone_recipe(rgb_mode, recipe), post_n)
            var_lum = luminance(var_rgb).astype(np.float32)
            var_budget = max(80, edge_budget // 2)
            edges_px, _emap = edge_polylines_from_lum(
                var_lum,
                contour_simplify=csimp,
                jitter=0.0,
                seed=i * 17,
                max_paths=var_budget,
                scan_knobs=sknobs,
            )
            ink_maps.append(polylines_to_ink_map(edges_px, height=h_px, width=w_px, stroke_radius=1))
            recipe_ids.append(recipe.id)
            variant_edge_counts.append(len(edges_px))
        t_variants = time.perf_counter()

        consensus = consensus_from_ink_maps(ink_maps, core_votes=2, fill_votes=1)
        # Over-extract from consensus, then face-budget / island kill / arc repair
        raw6 = contours_from_edge_mask(
            consensus,
            simplify=csimp,
            jitter=jitter,
            seed=99,
            max_paths=min(edge_budget * 2, edge_budget + 200),
        )
        from botdraw.portrait.linedraw_edges import prepare_luma_for_edges

        lum_u8 = prepare_luma_for_edges(lum.astype(np.float32))
        edges_px6 = refine_edge_polylines(raw6, lum_u8, max_paths=edge_budget)
        edge_polys = polylines_to_mm(edges_px6, img_w=w_px, img_h=h_px, page_w=page_w, page_h=page_h)
        edges = consensus.astype(np.float32) * 255.0
        # Placeholder; tone-grid hatch replaces ad-hoc hatch below
        hatch_polys = []
        ensemble_meta = {
            "enabled": True,
            "mode": "blur_pyramid",
            "recipes": recipe_ids,
            "variant_edge_counts": variant_edge_counts,
            "core_votes": 2,
            "fill_votes": 1,
            "consensus_ink_px": int(consensus.sum()),
            "refine": "face_budget+island_kill+arc_repair",
        }
    else:
        edge_polys, _legacy_hatch, edges = linedraw_edges_and_hatch(
            lum.astype(np.float32),
            page_w=page_w,
            page_h=page_h,
            contour_simplify=csimp,
            hatch_size=hsize,
            jitter=jitter,
            seed=0,
            max_edge_paths=edge_budget,
            max_hatch_paths=hatch_budget,
            scan_knobs=sknobs,
        )
        hatch_polys = []  # filled from tone grid

    # Intensity tone grid → coded hatch (booth: codes 0–3; studio: allow scribble code 4)
    # hatch_size <= 0 disables midtone hatch (structure-only ingest)
    max_tone_code = 3 if quality_enum == QualityPreset.BOOTH_FAST else 4
    if hsize <= 0:
        tone_pack = {
            "tone_grid": np.zeros((1, 1), dtype=np.float32),
            "tone_codes": np.zeros((1, 1), dtype=np.uint8),
            "tone_cell_px": 0.0,
            "tone_cell_mm": 0.0,
            "tone_origin_mm": (0.0, 0.0),
            "grid_shape": (1, 1),
        }
        hatch_polys = []
    else:
        tone_pack = build_tone_grid(
            lum.astype(np.float32),
            ink_target,
            cell_px=hsize,
            edge_map=np.asarray(edges, dtype=np.float32),
            page_w_mm=page_w,
            page_h_mm=page_h,
            max_code=max_tone_code,
        )
        hatch_polys = strokes_from_tone_grid(
            tone_pack["tone_codes"],
            cell_px=tone_pack["tone_cell_px"],
            img_w=int(rgb.shape[1]),
            img_h=int(rgb.shape[0]),
            page_w=page_w,
            page_h=page_h,
            style="hatch",
            jitter=jitter,
            seed=1,
            max_paths=hatch_budget,
        )
        if not hatch_polys:
            # Fallback to classic linedraw hatch if grid skipped everything
            lum_fallback = autocontrast_lum(lum.astype(np.float32), cutoff=10.0).astype(np.float32)
            hatch_px = hatch_from_lum(
                lum_fallback,
                hatch_size=hsize,
                jitter=jitter,
                seed=1,
                max_paths=hatch_budget,
            )
            hatch_polys = polylines_to_mm(
                hatch_px,
                img_w=int(rgb.shape[1]),
                img_h=int(rgb.shape[0]),
                page_w=page_w,
                page_h=page_h,
            )
    t_edges = time.perf_counter()

    region_budget = min(
        max_paths // 3,
        80 if quality_enum == QualityPreset.BOOTH_FAST else (200 if quality_enum == QualityPreset.BOOTH_BALANCED else 500),
    )
    if sknobs.get("region_boost"):
        region_budget = min(max_paths // 2, max(region_budget, region_budget * 2))
    regions = _vtracer_regions(
        rgb,
        mode=mode,
        quality=quality_enum,
        page_w=page_w,
        page_h=page_h,
        max_regions=region_budget,
        filter_speckle=speckle,
        min_path_points=min_pts,
        min_area_px=80.0 if quality_enum == QualityPreset.BOOTH_FAST else 48.0,
    )
    t_trace = time.perf_counter()

    # Build color clusters from regions (fallback: tone quantiles)
    clusters: list[ColorCluster] = []
    if regions:
        for r in regions[:24]:
            clusters.append(ColorCluster(id=r.id, mean_rgb=r.mean_rgb, area=r.area))
    else:
        for i, q in enumerate((20, 40, 60, 80)):
            mask = lum <= np.percentile(lum, q)
            if not np.any(mask):
                continue
            mean = tuple(float(x) for x in rgb[mask].mean(axis=0))
            clusters.append(ColorCluster(id=f"c{i}", mean_rgb=mean, area=float(mask.sum())))

    h, w = rgb.shape[:2]
    ingest_id = uuid4().hex[:12]
    timing: dict[str, float] = {
        "preprocess": round(t_pre - t0, 4),
        "edges": round(t_edges - t_pre, 4),
        "trace": round(t_trace - t_edges, 4),
        "total": round(t_trace - t0, 4),
    }
    if use_ensemble:
        timing["ensemble_variants"] = round(t_variants - t_pre, 4)
        timing["ensemble_consensus"] = round(t_edges - t_variants, 4)
    return PortraitVector(
        width_px=w,
        height_px=h,
        page_w_mm=page_w,
        page_h_mm=page_h,
        rgb=rgb,
        lum=lum.astype(np.float32),
        ink_target=ink_target,
        edge_map=edges,
        edge_polylines_mm=edge_polys,
        hatch_polylines_mm=hatch_polys,
        tone_grid=tone_pack["tone_grid"],
        tone_codes=tone_pack["tone_codes"],
        tone_cell_mm=float(tone_pack["tone_cell_mm"]),
        tone_origin_mm=tuple(tone_pack["tone_origin_mm"]),
        regions=regions,
        clusters=clusters,
        crop=crop_r,
        image_mode=mode or "photo",
        quality=quality_enum.value,
        ingest_id=ingest_id,
        meta={
            "timing_s": timing,
            "edge_count": len(edge_polys),
            "hatch_count": len(hatch_polys),
            "region_count": len(regions),
            "max_paths": max_paths,
            "auto_frame": auto_frame and (crop is None),
            "posterize_levels": post_n,
            "filter_speckle": speckle,
            "min_path_points": min_pts,
            "contrast": float(contrast),
            "contour_simplify": csimp,
            "hatch_size": hsize,
            "linedraw_jitter": jitter,
            "edge_extractor": "linedraw_ensemble" if use_ensemble else "linedraw",
            "ensemble": ensemble_meta,
            "scan_mode": scan,
            "tone_grid": {
                "cell_px": float(tone_pack["tone_cell_px"]),
                "cell_mm": float(tone_pack["tone_cell_mm"]),
                "origin_mm": list(tone_pack["tone_origin_mm"]),
                "shape": list(tone_pack["grid_shape"]),
                "max_code": max_tone_code,
                "code_hist": {
                    str(c): int((tone_pack["tone_codes"] == c).sum()) for c in range(6)
                },
            },
            "edge_prep": "prepare_luma_for_edges",
        },
    )
