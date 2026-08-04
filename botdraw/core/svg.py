"""SVG layer composition and export."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from botdraw.core.models import LayeredSVG, PaletteSet, PassLayer, Polyline


def _poly_to_d(points: list[tuple[float, float]], closed: bool = False) -> str:
    if not points:
        return ""
    parts = [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
    for x, y in points[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    if closed:
        parts.append("Z")
    return " ".join(parts)


def layered_to_svg_string(
    layered: LayeredSVG,
    palette: PaletteSet,
    *,
    paper_color_hex: str | None = None,
) -> str:
    ink_ns = "http://www.inkscape.org/namespaces/inkscape"
    sod_ns = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "xmlns:inkscape": ink_ns,
            "xmlns:sodipodi": sod_ns,
            "width": f"{layered.width_mm}mm",
            "height": f"{layered.height_mm}mm",
            "viewBox": f"0 0 {layered.width_mm} {layered.height_mm}",
        },
    )
    fill = paper_color_hex or (layered.meta or {}).get("paper_color_hex") or "#f7f1e8"
    ET.SubElement(
        root,
        "rect",
        {
            "x": "0",
            "y": "0",
            "width": str(layered.width_mm),
            "height": str(layered.height_mm),
            "fill": fill,
        },
    )
    for idx, pass_layer in enumerate(layered.passes, start=1):
        pen = palette.pen_by_id(pass_layer.pen_id)
        opacity = (
            pass_layer.opacity_override
            if pass_layer.opacity_override is not None
            else pen.profile.opacity
        )
        # Stroke-only groups (AxiDraw default: plot strokes, ignore fills)
        group = ET.SubElement(
            root,
            "g",
            {
                "id": f"pass-{idx:02d}-{pass_layer.id}",
                "data-pass-id": pass_layer.id,
                "data-pen-id": pass_layer.pen_id,
                "fill": "none",
                "stroke": pen.color_hex,
                "stroke-width": str(pen.profile.width_mm),
                "stroke-opacity": str(opacity),
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
            },
        )
        # True Inkscape layers (plot-by-layer in AxiDraw extension)
        group.set(f"{{{ink_ns}}}label", pass_layer.name)
        group.set(f"{{{ink_ns}}}groupmode", "layer")
        for poly in pass_layer.polylines:
            if len(poly.points) < 2:
                continue
            ET.SubElement(
                group,
                "path",
                {"d": _poly_to_d(poly.points, poly.closed)},
            )
    return ET.tostring(root, encoding="unicode")


def save_svg(
    layered: LayeredSVG,
    palette: PaletteSet,
    path: str | Path,
    *,
    paper_color_hex: str | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        layered_to_svg_string(layered, palette, paper_color_hex=paper_color_hex),
        encoding="utf-8",
    )
    return path


def merge_layered(*pieces: LayeredSVG) -> LayeredSVG:
    if not pieces:
        raise ValueError("No layers to merge")
    base = pieces[0]
    passes: list[PassLayer] = []
    for piece in pieces:
        passes.extend(piece.passes)
    return LayeredSVG(
        width_mm=base.width_mm,
        height_mm=base.height_mm,
        passes=passes,
        seed=base.seed,
        meta={k: v for p in pieces for k, v in p.meta.items()},
    )


def make_pass(
    pass_id: str,
    name: str,
    pen_id: str,
    polylines: list[Polyline],
    *,
    kind: str = "ink",
    opacity_override: float | None = None,
) -> PassLayer:
    return PassLayer(
        id=pass_id,
        name=name,
        pen_id=pen_id,
        polylines=polylines,
        kind=kind,
        opacity_override=opacity_override,
    )
