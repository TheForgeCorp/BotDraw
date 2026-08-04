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


def _parse_svg_paths(svg_text: str) -> list[list[tuple[float, float]]]:
    """Extract polygon-ish polylines from vtracer SVG path data (M/L/Z focus)."""
    root = ET.fromstring(svg_text)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    out: list[list[tuple[float, float]]] = []
    for el in root.iter(f"{ns}path"):
        d = el.attrib.get("d") or ""
        pts: list[tuple[float, float]] = []
        nums: list[float] = []
        cmd = "M"
        tokens = _PATH_CMD.findall(d)
        flat: list[str] = []
        for a, b in tokens:
            flat.append(a or b)
        i = 0
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
            if cmd in ("M", "L", "m", "l") and len(nums) >= 2:
                x, y = nums[0], nums[1]
                nums = nums[2:]
                if cmd in ("m", "l") and pts:
                    x += pts[-1][0]
                    y += pts[-1][1]
                pts.append((x, y))
                if cmd == "M":
                    cmd = "L"
                elif cmd == "m":
                    cmd = "l"
            elif cmd in ("H", "h") and len(nums) >= 1:
                x = nums.pop(0)
                y = pts[-1][1] if pts else 0.0
                if cmd == "h" and pts:
                    x += pts[-1][0]
                pts.append((x, y))
            elif cmd in ("V", "v") and len(nums) >= 1:
                y = nums.pop(0)
                x = pts[-1][0] if pts else 0.0
                if cmd == "v" and pts:
                    y += pts[-1][1]
                pts.append((x, y))
            elif cmd in ("Z", "z"):
                if pts and pts[0] != pts[-1]:
                    pts.append(pts[0])
                nums.clear()
        if len(pts) >= 3:
            out.append(pts)
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


def _edge_polylines(edge_map: np.ndarray, *, step: int, max_paths: int, page_w: float, page_h: float) -> list[list[tuple[float, float]]]:
    """Horizontal run extraction on edge map → simplified mm polylines."""
    h, w = edge_map.shape
    thr = max(20.0, float(np.percentile(edge_map, 85)))
    runs: list[tuple[float, list[tuple[float, float]]]] = []
    for y in range(0, h, max(1, step)):
        row = edge_map[y]
        run = None
        for x in range(w):
            on = row[x] >= thr
            if on and run is None:
                run = x
            elif not on and run is not None:
                if x - run >= 2:
                    ink = float(row[run:x].mean())
                    pts = [(float(run), float(y)), (float(x), float(y))]
                    runs.append((ink * (x - run), pts))
                run = None
        if run is not None and w - run >= 2:
            ink = float(row[run:].mean())
            runs.append((ink * (w - run), [(float(run), float(y)), (float(w - 1), float(y))]))
    runs.sort(key=lambda t: -t[0])
    out: list[list[tuple[float, float]]] = []
    for _, pts in runs[:max_paths]:
        mm = [map_to_page(x, y, img_w=w, img_h=h, page_w=page_w, page_h=page_h) for x, y in pts]
        try:
            simple = list(LineString(mm).simplify(0.15, preserve_topology=False).coords)
            if len(simple) >= 2:
                out.append([(float(a), float(b)) for a, b in simple])
        except Exception:
            out.append(mm)
    return out


def _vtracer_regions(
    rgb: np.ndarray,
    *,
    mode: str,
    quality: QualityPreset,
    page_w: float,
    page_h: float,
    max_regions: int,
) -> list[RegionPoly]:
    h, w = rgb.shape[:2]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    try:
        import vtracer
    except ImportError:
        return []

    binary = mode in ("drawing", "lineart") or quality == QualityPreset.BOOTH_FAST
    filter_speckle = 8 if quality == QualityPreset.BOOTH_FAST else (4 if quality == QualityPreset.BOOTH_BALANCED else 2)
    layer_diff = 32 if quality == QualityPreset.BOOTH_FAST else (20 if quality == QualityPreset.BOOTH_BALANCED else 12)

    with TemporaryDirectory() as td:
        inp = Path(td) / "in.png"
        outp = Path(td) / "out.svg"
        img.save(inp)
        kwargs: dict[str, Any] = {
            "colormode": "binary" if binary else "color",
            "mode": "polygon",
            "filter_speckle": filter_speckle,
            "corner_threshold": 60,
            "path_precision": 2,
        }
        if not binary:
            kwargs["hierarchical"] = "stacked"
            kwargs["layer_difference"] = layer_diff
            kwargs["color_precision"] = 6 if quality != QualityPreset.STUDIO_HQ else 8
        try:
            vtracer.convert_image_to_svg_py(str(inp), str(outp), **kwargs)
            svg = outp.read_text(encoding="utf-8")
        except Exception:
            return []

    paths = _parse_svg_paths(svg)
    # Sort by area descending, budget trim
    scored: list[tuple[float, list[tuple[float, float]]]] = []
    for pts in paths:
        a = _poly_area(pts)
        if a < 4:
            continue
        scored.append((a, pts))
    scored.sort(key=lambda t: -t[0])

    regions: list[RegionPoly] = []
    for i, (area, pts_px) in enumerate(scored[:max_regions]):
        mean = _mean_rgb_in_poly(rgb, pts_px)
        pts_mm = [
            map_to_page(x, y, img_w=w, img_h=h, page_w=page_w, page_h=page_h) for x, y in pts_px
        ]
        # Resample / simplify
        try:
            if len(pts_mm) >= 3:
                pts_mm = [(float(a), float(b)) for a, b in LineString(pts_mm).simplify(0.25).coords]
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


def _preprocess_array(rgb: np.ndarray, mode: str) -> np.ndarray:
    """Apply image_mode transforms on an already-loaded RGB array."""
    m = (mode or "photo").lower()
    if m == "photo":
        return rgb
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
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
    return np.asarray(img, dtype=np.float32)


def ingest_portrait(
    image_path: str | Path | None = None,
    *,
    image_array: np.ndarray | None = None,
    mode: str = "photo",
    quality: QualityPreset | str = QualityPreset.BOOTH_BALANCED,
    paper: PaperSize | str = PaperSize.A4,
    crop: CropRect | dict | None = None,
    auto_frame: bool = True,
) -> PortraitVector:
    """Load/crop/preprocess image and build PortraitVector (tone + edges + regions)."""
    t0 = time.perf_counter()
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
    paper_enum = paper if isinstance(paper, PaperSize) else PaperSize(paper)
    limits = QUALITY_LIMITS[quality_enum]
    max_side = int(limits["image_max"])
    max_paths = int(limits["max_paths"])
    page_w, page_h = PAPER_MM[paper_enum]

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

    rgb = np.asarray(img, dtype=np.float32)
    rgb = _preprocess_array(rgb, mode)
    t_pre = time.perf_counter()

    lum = luminance(rgb)
    ink_target = np.clip(1.0 - lum / 255.0, 0.0, 1.0).astype(np.float32)

    # Edge map
    g = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L")
    edges = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    edge_step = 4 if quality_enum == QualityPreset.BOOTH_FAST else (3 if quality_enum == QualityPreset.BOOTH_BALANCED else 2)
    edge_budget = min(max_paths // 2, 400 if quality_enum == QualityPreset.BOOTH_FAST else (1200 if quality_enum == QualityPreset.BOOTH_BALANCED else 4000))
    edge_polys = _edge_polylines(edges, step=edge_step, max_paths=edge_budget, page_w=page_w, page_h=page_h)
    t_edges = time.perf_counter()

    region_budget = min(max_paths // 3, 80 if quality_enum == QualityPreset.BOOTH_FAST else (200 if quality_enum == QualityPreset.BOOTH_BALANCED else 500))
    regions = _vtracer_regions(
        rgb,
        mode=mode,
        quality=quality_enum,
        page_w=page_w,
        page_h=page_h,
        max_regions=region_budget,
    )
    t_trace = time.perf_counter()

    # Build color clusters from regions (fallback: tone quantiles)
    clusters: list[ColorCluster] = []
    if regions:
        for r in regions[:24]:
            clusters.append(
                ColorCluster(id=r.id, mean_rgb=r.mean_rgb, area=r.area)
            )
    else:
        for i, q in enumerate((20, 40, 60, 80)):
            mask = lum <= np.percentile(lum, q)
            if not np.any(mask):
                continue
            mean = tuple(float(x) for x in rgb[mask].mean(axis=0))
            clusters.append(ColorCluster(id=f"c{i}", mean_rgb=mean, area=float(mask.sum())))

    h, w = rgb.shape[:2]
    ingest_id = uuid4().hex[:12]
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
        regions=regions,
        clusters=clusters,
        crop=crop_r,
        image_mode=mode or "photo",
        quality=quality_enum.value,
        ingest_id=ingest_id,
        meta={
            "timing_s": {
                "preprocess": round(t_pre - t0, 4),
                "edges": round(t_edges - t_pre, 4),
                "trace": round(t_trace - t_edges, 4),
                "total": round(t_trace - t0, 4),
            },
            "edge_count": len(edge_polys),
            "region_count": len(regions),
            "max_paths": max_paths,
            "auto_frame": auto_frame and (crop is None),
        },
    )
