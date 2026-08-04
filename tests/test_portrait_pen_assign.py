"""Pen assignment auto + overrides."""

from __future__ import annotations

from botdraw.core.models import QualityPreset
from botdraw.core.svg import layered_to_svg_string
from botdraw.palettes import load_palette
from botdraw.portrait import assign_pens, ingest_portrait, apply_pen_overrides, render_from_vector
from botdraw.core.models import StyleParams


def test_auto_assign_excludes_highlighter_for_edge():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal)
    assert "edge" in pv.pen_map
    edge = pal.pen_by_id(pv.pen_map["edge"])
    assert edge.profile.nib_type.value != "highlighter"
    assert pv.meta.get("pen_assignment")


def test_pen_map_override_wins():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal, pen_map={"edge": "crimson"})
    assert pv.pen_map["edge"] == "crimson"


def test_pen_overrides_width_in_svg():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pal = apply_pen_overrides(pal, {"black": {"width_mm": 1.25, "color_hex": "#111111"}})
    pv = assign_pens(pv, pal, pen_map={"edge": "black"})
    layered = render_from_vector(
        "portrait_linework",
        pv,
        pal,
        StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=1.0),
    )
    svg = layered_to_svg_string(layered, pal, paper_color_hex="#fff")
    assert "1.25" in svg
    assert 'fill="#fff"' in svg or "fill=\"#fff\"" in svg


def test_edge_prefers_narrower_nib():
    pv = ingest_portrait(mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal)
    edge = pal.pen_by_id(pv.pen_map["edge"])
    ink = [p for p in pal.pens if p.profile.nib_type.value != "highlighter"]
    assert edge.profile.width_mm <= max(p.profile.width_mm for p in ink)
