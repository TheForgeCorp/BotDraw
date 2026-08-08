"""
Portrait rendering fidelity metrics.

Compares the plotted ink raster of a rendered ``LayeredSVG`` against the
source photo's ink target (``PortraitVector.ink_target``), in the same page
frame that ``map_to_page`` defines for every restyler.

This exists because every prior portrait test asserted structure/counts
("are there edges", "is hatch_count > 0") and none asked "does the ink
land where the photo is dark" — which is precisely the class of bug (tone
gate excluding dark areas, palette quantization scattering hue) that let
garbled real-photo output ship while the whole suite stayed green.

No SVG rasterizer needed: every ``LayeredSVG`` pass renders with
``fill="none"`` (see ``botdraw/core/svg.py``) and the plotter emulator only
strokes, so redrawing each polyline with Pillow's ``ImageDraw.line`` at the
assigned pen width reproduces exactly what gets plotted.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

from botdraw.core.models import LayeredSVG, PaletteSet
from botdraw.portrait.models import PortraitVector
from botdraw.styles.image_utils import map_to_page

# ~4 px/mm resolves pen widths (0.3-1mm) without being slow to rasterize.
PX_PER_MM = 4.0


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) < 6:
        return (0, 0, 0)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rasterize_ink(
    layered: LayeredSVG,
    palette: PaletteSet,
    *,
    px_per_mm: float = PX_PER_MM,
    pass_ids: set[str] | None = None,
) -> np.ndarray:
    """
    Grayscale ink-density raster (0 = bare paper, 1 = fully inked) of the
    given passes (default: all), at the plotted pen widths.
    """
    w_px = max(1, int(round(layered.width_mm * px_per_mm)))
    h_px = max(1, int(round(layered.height_mm * px_per_mm)))
    img = Image.new("L", (w_px, h_px), 0)
    draw = ImageDraw.Draw(img)
    for p in layered.passes:
        if pass_ids is not None and p.id not in pass_ids:
            continue
        try:
            pen = palette.pen_by_id(p.pen_id)
            width_mm = pen.profile.width_mm
        except KeyError:
            width_mm = 0.4
        width_px = max(1, int(round(width_mm * px_per_mm)))
        for poly in p.polylines:
            pts = list(poly.points)
            if not pts:
                continue
            if poly.closed and len(pts) >= 2 and pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            xy = [(x * px_per_mm, y * px_per_mm) for x, y in pts]
            if len(xy) >= 2:
                draw.line(xy, fill=255, width=width_px)
            else:
                r = width_px / 2.0
                x, y = xy[0]
                draw.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return np.asarray(img, dtype=np.float32) / 255.0


def ink_target_on_page(
    pv: PortraitVector,
    *,
    width_mm: float,
    height_mm: float,
    px_per_mm: float = PX_PER_MM,
) -> np.ndarray:
    """
    Resample ``PortraitVector.ink_target`` (source-photo darkness, 0..1, in
    source image pixel space) into the same page pixel grid ``rasterize_ink``
    produces, using the identical ``map_to_page`` transform every restyler
    uses to place edges/hatch. This is what makes the two rasters comparable.
    """
    target = np.clip(np.asarray(pv.ink_target, dtype=np.float32), 0.0, 1.0)
    h_img, w_img = target.shape[:2]
    out_w = max(1, int(round(width_mm * px_per_mm)))
    out_h = max(1, int(round(height_mm * px_per_mm)))
    canvas = np.zeros((out_h, out_w), dtype=np.float32)
    if h_img == 0 or w_img == 0:
        return canvas

    x0, y0 = map_to_page(0, 0, img_w=w_img, img_h=h_img, page_w=width_mm, page_h=height_mm)
    x1, y1 = map_to_page(w_img, h_img, img_w=w_img, img_h=h_img, page_w=width_mm, page_h=height_mm)
    dst_w = max(1, int(round((x1 - x0) * px_per_mm)))
    dst_h = max(1, int(round((y1 - y0) * px_per_mm)))

    resized = Image.fromarray((target * 255).astype(np.uint8)).resize(
        (dst_w, dst_h), Image.Resampling.BILINEAR
    )
    arr = np.asarray(resized, dtype=np.float32) / 255.0

    paste_x = int(round(x0 * px_per_mm))
    paste_y = int(round(y0 * px_per_mm))
    dst_x0, dst_y0 = max(0, paste_x), max(0, paste_y)
    dst_x1, dst_y1 = min(out_w, paste_x + dst_w), min(out_h, paste_y + dst_h)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return canvas
    src_x0, src_y0 = dst_x0 - paste_x, dst_y0 - paste_y
    src_x1, src_y1 = src_x0 + (dst_x1 - dst_x0), src_y0 + (dst_y1 - dst_y0)
    canvas[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]
    return canvas


def render_preview_png(
    layered: LayeredSVG,
    palette: PaletteSet,
    *,
    max_side: int = 420,
    paper_rgb: tuple[int, int, int] = (247, 241, 232),
) -> bytes:
    """
    True-color raster of a rendered style, at plotted pen widths — the
    contact-sheet preview. Same no-SVG-renderer-needed reasoning as
    ``rasterize_ink``, just in color instead of ink density.
    """
    px_per_mm = max_side / max(layered.width_mm, layered.height_mm)
    w_px = max(1, int(round(layered.width_mm * px_per_mm)))
    h_px = max(1, int(round(layered.height_mm * px_per_mm)))
    img = Image.new("RGB", (w_px, h_px), paper_rgb)
    draw = ImageDraw.Draw(img)
    for p in layered.passes:
        try:
            pen = palette.pen_by_id(p.pen_id)
        except KeyError:
            continue
        color = _hex_to_rgb(pen.color_hex)
        width_px = max(1, int(round(pen.profile.width_mm * px_per_mm)))
        for poly in p.polylines:
            pts = list(poly.points)
            if not pts:
                continue
            if poly.closed and len(pts) >= 2 and pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            xy = [(x * px_per_mm, y * px_per_mm) for x, y in pts]
            if len(xy) >= 2:
                draw.line(xy, fill=color, width=width_px)
            else:
                r = width_px / 2.0
                x, y = xy[0]
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@dataclass
class FidelityReport:
    """
    tone_corr > 0: ink lands where the photo is dark (plausible likeness).
    tone_corr < 0: ink lands where the photo is *bright* — the exact defect
    measured in the classic path on real headshots (~-0.29).
    """

    tone_corr: float
    total_coverage: float
    max_single_pass_coverage: float
    max_single_pass_id: str | None
    pass_coverage: dict[str, float] = field(default_factory=dict)


def score_render(
    layered: LayeredSVG,
    palette: PaletteSet,
    pv: PortraitVector,
    *,
    px_per_mm: float = PX_PER_MM,
) -> FidelityReport:
    """Fidelity metrics for one rendered style against its source photo."""
    ink = rasterize_ink(layered, palette, px_per_mm=px_per_mm)
    target = ink_target_on_page(
        pv, width_mm=layered.width_mm, height_mm=layered.height_mm, px_per_mm=px_per_mm
    )

    flat_ink, flat_target = ink.reshape(-1), target.reshape(-1)
    if flat_ink.std() < 1e-6 or flat_target.std() < 1e-6:
        tone_corr = 0.0
    else:
        tone_corr = float(np.corrcoef(flat_ink, flat_target)[0, 1])
        if not np.isfinite(tone_corr):
            tone_corr = 0.0

    total_px = float(ink.size)
    total_coverage = float((ink > 0.5).sum()) / total_px

    pass_coverage: dict[str, float] = {}
    max_cov, max_id = 0.0, None
    for p in layered.passes:
        pass_ink = rasterize_ink(layered, palette, px_per_mm=px_per_mm, pass_ids={p.id})
        cov = float((pass_ink > 0.5).sum()) / total_px
        pass_coverage[p.id] = cov
        if cov > max_cov:
            max_cov, max_id = cov, p.id

    return FidelityReport(
        tone_corr=tone_corr,
        total_coverage=total_coverage,
        max_single_pass_coverage=max_cov,
        max_single_pass_id=max_id,
        pass_coverage=pass_coverage,
    )
