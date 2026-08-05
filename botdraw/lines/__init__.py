"""Line Library presets (stroke ornament stocks)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel

from botdraw.core.models import Polyline
from botdraw.portrait.ornament import StrokeOrnamentParams, decorate_polyline

PRESET_DIR = Path(__file__).parent / "presets"
USER_DIR = Path(__file__).resolve().parents[2] / "jobs" / "lines"

DEFAULT_LINE_ID = "solid"


class LineStock(BaseModel):
    id: str
    name: str
    line_type: str = "solid"
    line_spacing_mm: float = 1.2
    pattern_period_mm: float = 2.0
    pattern_amplitude_mm: float = 0.8
    dash_mm: float = 2.0
    gap_mm: float = 1.2
    ornament_target: str = "all"  # all | edges | fills
    notes: str = ""


def _ensure_presets() -> None:
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    seeds = [
        LineStock(id="solid", name="Solid", line_type="solid", notes="Plain centerline"),
        LineStock(
            id="dashed",
            name="Dashed",
            line_type="dashed",
            dash_mm=3.0,
            gap_mm=1.5,
        ),
        LineStock(
            id="dotted",
            name="Dotted",
            line_type="dotted",
            dash_mm=0.35,
            gap_mm=1.4,
        ),
        LineStock(
            id="wave",
            name="Wave",
            line_type="wave",
            pattern_period_mm=3.0,
            pattern_amplitude_mm=1.0,
        ),
        LineStock(
            id="zigzag",
            name="Zigzag",
            line_type="zigzag",
            pattern_period_mm=2.5,
            pattern_amplitude_mm=1.2,
        ),
        LineStock(
            id="stitch",
            name="Stitch",
            line_type="stitch",
            dash_mm=2.0,
            gap_mm=1.0,
        ),
        LineStock(
            id="railroad",
            name="Railroad",
            line_type="railroad",
            line_spacing_mm=1.6,
            pattern_period_mm=2.5,
            pattern_amplitude_mm=0.8,
        ),
        LineStock(
            id="chevron",
            name="Chevron",
            line_type="chevron",
            pattern_period_mm=3.0,
            pattern_amplitude_mm=1.2,
        ),
        LineStock(
            id="double",
            name="Double",
            line_type="double",
            line_spacing_mm=1.4,
        ),
        LineStock(
            id="hatch-tick",
            name="Hatch Tick",
            line_type="hatch_tick",
            pattern_period_mm=2.0,
            pattern_amplitude_mm=1.0,
        ),
    ]
    for s in seeds:
        path = PRESET_DIR / f"{s.id}.json"
        if not path.exists():
            path.write_text(s.model_dump_json(indent=2), encoding="utf-8")


def _ensure_user_dir() -> Path:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DIR


def list_line_ids() -> list[str]:
    _ensure_presets()
    ids = {p.stem for p in PRESET_DIR.glob("*.json")}
    if USER_DIR.exists():
        ids |= {p.stem for p in USER_DIR.glob("*.json")}
    return sorted(ids)


def load_line(line_id: str | None = None) -> LineStock:
    _ensure_presets()
    lid = line_id or DEFAULT_LINE_ID
    for folder in (USER_DIR, PRESET_DIR):
        path = folder / f"{lid}.json"
        if path.exists():
            return LineStock.model_validate_json(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Line not found: {lid}")


def list_lines() -> list[dict]:
    return [load_line(lid).model_dump() for lid in list_line_ids()]


def save_line(stock: LineStock) -> Path:
    path = _ensure_user_dir() / f"{stock.id}.json"
    path.write_text(stock.model_dump_json(indent=2), encoding="utf-8")
    return path


def delete_line(line_id: str) -> None:
    """Delete a user line. Raises PermissionError for presets, FileNotFoundError if missing."""
    _ensure_presets()
    user_path = USER_DIR / f"{line_id}.json"
    if user_path.exists():
        user_path.unlink()
        return
    if (PRESET_DIR / f"{line_id}.json").exists():
        raise PermissionError(f"Cannot delete preset line: {line_id}")
    raise FileNotFoundError(f"Line not found: {line_id}")


def to_ornament_params(stock: LineStock) -> StrokeOrnamentParams:
    return StrokeOrnamentParams(
        line_type=stock.line_type,
        line_spacing_mm=stock.line_spacing_mm,
        pattern_period_mm=stock.pattern_period_mm,
        pattern_amplitude_mm=stock.pattern_amplitude_mm,
        dash_mm=stock.dash_mm,
        gap_mm=stock.gap_mm,
        ornament_target=stock.ornament_target,
    )


def _poly_to_d(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    parts = [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
    for x, y in points[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    return " ".join(parts)


def preview_svg(stock: LineStock, *, width_mm: float = 80, height_mm: float = 24) -> str:
    """Sample horizontal polyline decorated via ornament; return SVG string."""
    margin_x = 4.0
    y = height_mm / 2.0
    sample = Polyline(
        points=[(margin_x, y), (width_mm - margin_x, y)],
        pen_id="preview",
    )
    decorated = decorate_polyline(sample, to_ornament_params(stock))

    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": f"{width_mm}mm",
            "height": f"{height_mm}mm",
            "viewBox": f"0 0 {width_mm} {height_mm}",
        },
    )
    ET.SubElement(
        root,
        "rect",
        {
            "x": "0",
            "y": "0",
            "width": str(width_mm),
            "height": str(height_mm),
            "fill": "#f7f1e8",
        },
    )
    group = ET.SubElement(
        root,
        "g",
        {
            "fill": "none",
            "stroke": "#1a1a1a",
            "stroke-width": "0.45",
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        },
    )
    for poly in decorated:
        if len(poly.points) < 2:
            continue
        ET.SubElement(group, "path", {"d": _poly_to_d(list(poly.points))})
    return ET.tostring(root, encoding="unicode")
