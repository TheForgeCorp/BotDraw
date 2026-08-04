"""Serialize PortraitVector for UI preview (no style/ornament)."""

from __future__ import annotations

import base64
import io
from typing import Any

import numpy as np
from PIL import Image

from botdraw.portrait.models import PortraitVector


def portrait_vector_preview_dict(
    pv: PortraitVector,
    *,
    include_preview_png: bool = True,
    max_edge_paths: int | None = None,
    max_hatch_paths: int | None = None,
    max_regions: int | None = None,
) -> dict[str, Any]:
    """Lightweight JSON for Ingest pane — polylines + crop + optional PNG."""
    edges = list(pv.edge_polylines_mm)
    hatch = list(pv.hatch_polylines_mm)
    regions = list(pv.regions)
    if max_edge_paths is not None:
        edges = edges[: max(0, int(max_edge_paths))]
    if max_hatch_paths is not None:
        hatch = hatch[: max(0, int(max_hatch_paths))]
    if max_regions is not None:
        regions = regions[: max(0, int(max_regions))]

    out: dict[str, Any] = {
        "ingest_id": pv.ingest_id,
        "crop": pv.crop.model_dump(),
        "timing_s": (pv.meta or {}).get("timing_s") or {},
        "edge_count": len(pv.edge_polylines_mm),
        "hatch_count": len(pv.hatch_polylines_mm),
        "region_count": len(pv.regions),
        "page_mm": [pv.page_w_mm, pv.page_h_mm],
        "width_px": pv.width_px,
        "height_px": pv.height_px,
        "image_mode": pv.image_mode,
        "quality": pv.quality,
        "edge_polylines_mm": edges,
        "hatch_polylines_mm": hatch,
        "regions": [
            {
                "id": r.id,
                "points_mm": r.points_mm,
                "mean_rgb": list(r.mean_rgb),
                "area": r.area,
                "pen_id": r.pen_id,
            }
            for r in regions
        ],
        "meta": {
            "edge_count": (pv.meta or {}).get("edge_count"),
            "hatch_count": (pv.meta or {}).get("hatch_count"),
            "region_count": (pv.meta or {}).get("region_count"),
            "auto_frame": (pv.meta or {}).get("auto_frame"),
            "posterize_levels": (pv.meta or {}).get("posterize_levels"),
            "filter_speckle": (pv.meta or {}).get("filter_speckle"),
            "min_path_points": (pv.meta or {}).get("min_path_points"),
            "contrast": (pv.meta or {}).get("contrast"),
            "contour_simplify": (pv.meta or {}).get("contour_simplify"),
            "hatch_size": (pv.meta or {}).get("hatch_size"),
            "linedraw_jitter": (pv.meta or {}).get("linedraw_jitter"),
            "edge_extractor": (pv.meta or {}).get("edge_extractor"),
            "line_source": (pv.meta or {}).get("line_source"),
            "ensemble": (pv.meta or {}).get("ensemble"),
            "scan_mode": (pv.meta or {}).get("scan_mode") or "auto",
            "tone_grid": (pv.meta or {}).get("tone_grid"),
            "edge_prep": (pv.meta or {}).get("edge_prep"),
        },
        "tone_cell_mm": float(pv.tone_cell_mm or 0.0),
        "has_tone_grid": pv.tone_codes is not None,
    }
    if include_preview_png:
        try:
            rgb = np.asarray(pv.rgb, dtype=np.float32)
            img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
            # Cap preview size for wire
            w, h = img.size
            max_side = 480
            scale = max_side / max(w, h)
            if scale < 1:
                img = img.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    Image.Resampling.LANCZOS,
                )
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            out["preview_png_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            out["preview_png_b64"] = None
        # Inkscape-style intermediate filter preview (brightness / edges / …)
        try:
            from botdraw.portrait.scan_modes import build_scan_intermediate, intermediate_to_png_b64

            scan = (pv.meta or {}).get("scan_mode") or "auto"
            inter = build_scan_intermediate(
                np.asarray(pv.lum, dtype=np.float32),
                np.asarray(pv.rgb, dtype=np.float32),
                scan,
                posterize_levels=int((pv.meta or {}).get("posterize_levels") or 6),
            )
            out["intermediate_png_b64"] = intermediate_to_png_b64(inter)
            out["scan_mode"] = scan
        except Exception:
            out["intermediate_png_b64"] = None
        # Tone-code heatmap underlay (coarse intensity recipes)
        try:
            if pv.tone_codes is not None:
                from botdraw.portrait.tone_grid import tone_codes_heatmap_rgb

                heat = tone_codes_heatmap_rgb(np.asarray(pv.tone_codes, dtype=np.uint8))
                himg = Image.fromarray(heat, mode="RGB")
                # Upscale to match photo preview size for overlay alignment
                tw = max(1, int(pv.width_px))
                th = max(1, int(pv.height_px))
                max_side = 480
                sc = max_side / max(tw, th)
                if sc < 1:
                    tw, th = max(1, int(tw * sc)), max(1, int(th * sc))
                himg = himg.resize((tw, th), Image.Resampling.NEAREST)
                buf = io.BytesIO()
                himg.save(buf, format="PNG", optimize=True)
                out["tone_heatmap_png_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
            else:
                out["tone_heatmap_png_b64"] = None
        except Exception:
            out["tone_heatmap_png_b64"] = None
    return out


def portrait_vector_raw_svg(
    pv: PortraitVector,
    *,
    paper_color_hex: str = "#f7f1e8",
    edge_color: str = "#0e7490",
    hatch_color: str = "#c2410c",
    region_color: str = "#a21caf",
) -> str:
    """Raw outline SVG: hatch + edges + region closed paths (no style)."""
    w, h = pv.page_w_mm, pv.page_h_mm

    def path_d(pts: list[tuple[float, float]], closed: bool = False) -> str:
        if len(pts) < 2:
            return ""
        parts = [f"M {pts[0][0]:.3f} {pts[0][1]:.3f}"]
        for x, y in pts[1:]:
            parts.append(f"L {x:.3f} {y:.3f}")
        if closed:
            parts.append("Z")
        return " ".join(parts)

    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
            f'width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">'
        ),
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="{paper_color_hex}"/>',
        (
            f'<g id="layer-hatch" inkscape:groupmode="layer" inkscape:label="2 Midtone hatch" '
            f'fill="none" stroke="{hatch_color}" stroke-width="0.25" stroke-opacity="0.75" stroke-linecap="round">'
        ),
    ]
    for i, pts in enumerate(pv.hatch_polylines_mm):
        d = path_d(list(pts), closed=False)
        if d:
            chunks.append(f'<path d="{d}" data-hatch="{i}"/>')
    chunks.append("</g>")
    chunks.append(
        f'<g id="layer-regions" inkscape:groupmode="layer" inkscape:label="3 Color bands" '
        f'fill="none" stroke="{region_color}" stroke-width="0.35" stroke-opacity="0.85">'
    )
    for r in pv.regions:
        d = path_d(list(r.points_mm), closed=True)
        if d:
            chunks.append(f'<path d="{d}" data-region="{r.id}"/>')
    chunks.append("</g>")
    chunks.append(
        f'<g id="layer-edges" inkscape:groupmode="layer" inkscape:label="1 Structure" '
        f'fill="none" stroke="{edge_color}" stroke-width="0.3" stroke-linecap="round">'
    )
    for i, pts in enumerate(pv.edge_polylines_mm):
        d = path_d(list(pts), closed=False)
        if d:
            chunks.append(f'<path d="{d}" data-edge="{i}"/>')
    chunks.append("</g>")
    chunks.append("</svg>")
    return "\n".join(chunks)
