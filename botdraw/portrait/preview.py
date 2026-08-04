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
    max_regions: int | None = None,
) -> dict[str, Any]:
    """Lightweight JSON for Ingest pane — polylines + crop + optional PNG."""
    edges = list(pv.edge_polylines_mm)
    regions = list(pv.regions)
    if max_edge_paths is not None:
        edges = edges[: max(0, int(max_edge_paths))]
    if max_regions is not None:
        regions = regions[: max(0, int(max_regions))]

    out: dict[str, Any] = {
        "ingest_id": pv.ingest_id,
        "crop": pv.crop.model_dump(),
        "timing_s": (pv.meta or {}).get("timing_s") or {},
        "edge_count": len(pv.edge_polylines_mm),
        "region_count": len(pv.regions),
        "page_mm": [pv.page_w_mm, pv.page_h_mm],
        "width_px": pv.width_px,
        "height_px": pv.height_px,
        "image_mode": pv.image_mode,
        "quality": pv.quality,
        "edge_polylines_mm": edges,
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
            "region_count": (pv.meta or {}).get("region_count"),
            "auto_frame": (pv.meta or {}).get("auto_frame"),
        },
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
    return out


def portrait_vector_raw_svg(
    pv: PortraitVector,
    *,
    paper_color_hex: str = "#f7f1e8",
    edge_color: str = "#0e7490",
    region_color: str = "#a21caf",
) -> str:
    """Raw outline SVG: edges + region closed paths (no hatch/style)."""
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
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">',
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="{paper_color_hex}"/>',
        f'<g id="regions" fill="none" stroke="{region_color}" stroke-width="0.35" stroke-opacity="0.85">',
    ]
    for r in pv.regions:
        d = path_d(list(r.points_mm), closed=True)
        if d:
            chunks.append(f'<path d="{d}" data-region="{r.id}"/>')
    chunks.append("</g>")
    chunks.append(
        f'<g id="edges" fill="none" stroke="{edge_color}" stroke-width="0.3" stroke-linecap="round">'
    )
    for i, pts in enumerate(pv.edge_polylines_mm):
        d = path_d(list(pts), closed=False)
        if d:
            chunks.append(f'<path d="{d}" data-edge="{i}"/>')
    chunks.append("</g>")
    chunks.append("</svg>")
    return "\n".join(chunks)
