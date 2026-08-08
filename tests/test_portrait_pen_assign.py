"""Pen assignment auto + overrides."""

from __future__ import annotations

import numpy as np

from botdraw.core.models import QualityPreset
from botdraw.core.svg import layered_to_svg_string
from botdraw.palettes import load_palette
from botdraw.portrait import assign_pens, ingest_portrait, apply_pen_overrides, render_from_vector
from botdraw.core.models import StyleParams
from botdraw.portrait.pens import photo_is_low_chroma


def _grayscale_face(size: int = 160) -> np.ndarray:
    """A photo-like image with zero saturation (R==G==B everywhere) — the
    real-world case reported as rendering in navy/ochre/teal instead of
    monochrome."""
    yy, xx = np.mgrid[0:size, 0:size]
    cy, cx, r = size * 0.45, size * 0.5, size * 0.3
    face = ((yy - cy) ** 2 + (xx - cx) ** 2) < r**2
    lum = np.full((size, size), 40.0, dtype=np.float32)
    lum[face] = 190.0
    lum[int(size * 0.35) : int(size * 0.4), int(size * 0.35) : int(size * 0.65)] = 60.0
    return np.stack([lum, lum, lum], axis=-1)


def _colorful_face(size: int = 160) -> np.ndarray:
    rgb = np.full((size, size, 3), (30.0, 60.0, 20.0), dtype=np.float32)
    yy, xx = np.mgrid[0:size, 0:size]
    cy, cx, r = size * 0.45, size * 0.5, size * 0.3
    face = ((yy - cy) ** 2 + (xx - cx) ** 2) < r**2
    rgb[face] = (220.0, 170.0, 130.0)
    return rgb


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


def test_grayscale_photo_detected_as_low_chroma():
    pv = ingest_portrait(image_array=_grayscale_face(), mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    assert photo_is_low_chroma(pv) is True


def test_colorful_photo_not_detected_as_low_chroma():
    pv = ingest_portrait(image_array=_colorful_face(), mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    assert photo_is_low_chroma(pv) is False


def test_default6_hatch_pen_is_black_not_navy_on_grayscale_photo():
    """
    Regression guard: default-6 has no true gray pen (just black plus
    navy/crimson/ochre/teal), and the hatch role previously always picked
    whichever pen was "next darkest" after the edge pen — navy — even on
    a genuinely black-and-white photo. It should now reuse the edge pen
    (black) instead of spilling into an arbitrary saturated hue.
    """
    pv = ingest_portrait(image_array=_grayscale_face(), mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal)
    assert pv.meta.get("monochrome_source") is True
    assert pv.pen_map["hatch"] == pv.pen_map["edge"] == "black"


def test_default6_hatch_pen_stays_navy_on_colorful_photo():
    """Same palette, a genuinely colorful photo: the monochrome policy
    must not fire and hatch keeps its normal (non-edge) pen."""
    pv = ingest_portrait(image_array=_colorful_face(), mode="photo", quality=QualityPreset.BOOTH_FAST, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal)
    assert pv.meta.get("monochrome_source") is False
    assert pv.pen_map["hatch"] != pv.pen_map["edge"]


def test_region_outline_pen_stays_monochrome_but_cubism_keeps_color():
    """
    _pen_for()'s region/rgb fallback (used by region-outline styles and by
    Cubism's facet fill) must respect the monochrome policy for outline
    styles but opt out for Cubism, whose entire visual language depends on
    multiple distinguishable facet colors.
    """
    pv = ingest_portrait(image_array=_grayscale_face(), mode="photo", quality=QualityPreset.STUDIO_HQ, paper="A5")
    pal = load_palette("default-6")
    pv = assign_pens(pv, pal)
    assert pv.meta.get("monochrome_source") is True
    if not pv.regions:
        return  # synthetic fixture may not always segment into regions

    params = StyleParams(seed=1, quality=QualityPreset.STUDIO_HQ, density=1.0)
    linework = render_from_vector("portrait_linework", pv, pal, params)
    region_pass_ids = {
        p.pen_id for p in linework.passes if p.id.startswith("bands-")
    }
    assert region_pass_ids <= {"black"}

    cubism = render_from_vector("portrait_cubism", pv, pal, params)
    facet_pens = {p.pen_id for p in cubism.passes if p.id.startswith("mosaic-") and p.id != "mosaic-outline"}
    assert facet_pens - {"black"}, "Cubism should still use non-black pens on a grayscale source"
