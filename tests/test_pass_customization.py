"""Per-pass customization: stable role identity + pen/visibility overrides."""
from __future__ import annotations

from botdraw.core.models import LayeredSVG, PaletteSet, Pen, Polyline, QualityPreset
from botdraw.core.pipeline import render_job
from botdraw.core.svg import make_pass
from botdraw.core.models import LineProfile
from botdraw.palettes import load_palette
from botdraw.portrait.customization import apply_pass_overrides, describe_passes


def _sample_layered() -> LayeredSVG:
    poly1 = Polyline(points=[(0.0, 0.0), (10.0, 10.0)], pen_id="navy")
    poly2 = Polyline(points=[(5.0, 5.0), (15.0, 15.0)], pen_id="crimson")
    return LayeredSVG(
        width_mm=100,
        height_mm=100,
        passes=[
            make_pass("bands-navy", "3 Color bands (navy)", "navy", [poly1], role="bands"),
            make_pass("bands-crimson", "3 Color bands (crimson)", "crimson", [poly2], role="bands"),
            make_pass("structure", "1 Structure", "black", [poly1]),
        ],
        meta={},
    )


def test_stable_role_falls_back_to_id_for_passes_without_role():
    p = make_pass("structure", "1 Structure", "black", [])
    assert p.role is None
    assert p.stable_role() == "structure"


def test_stable_role_uses_explicit_role_over_pen_derived_id():
    p = make_pass("bands-navy", "3 Color bands (navy)", "navy", [], role="bands")
    assert p.stable_role() == "bands"


def test_describe_passes_lists_stable_roles():
    layered = _sample_layered()
    rows = describe_passes(layered)
    roles = [r["role"] for r in rows]
    assert roles == ["bands", "bands", "structure"]


def test_pass_override_hides_a_role_entirely():
    layered = _sample_layered()
    pal = load_palette("default-6")
    out = apply_pass_overrides(layered, pal, {"structure": {"visible": False}})
    assert [p.id for p in out.passes] == ["bands-navy", "bands-crimson"]
    assert "structure" in out.meta["pass_overrides_applied"]


def test_pass_override_reassigns_pen_by_role_not_id():
    """
    The whole point: two passes share the role "bands" but have different
    ids (bands-navy, bands-crimson) because they're pen-derived. An
    override keyed by role must be able to independently target each pass
    that shares the role IF the override dict distinguishes them — but a
    single-key override like {"bands": {...}} applies uniformly to every
    pass with that role, matching how a pass's *category* (not its
    specific current pen) is the stable, user-facing concept.
    """
    layered = _sample_layered()
    pal = load_palette("default-6")
    out = apply_pass_overrides(layered, pal, {"bands": {"pen_id": "ochre"}})
    bands_passes = [p for p in out.passes if p.stable_role() == "bands"]
    assert len(bands_passes) == 2
    assert all(p.pen_id == "ochre" for p in bands_passes)
    assert all(pl.pen_id == "ochre" for p in bands_passes for pl in p.polylines)
    # untouched
    structure = next(p for p in out.passes if p.stable_role() == "structure")
    assert structure.pen_id == "black"


def test_pass_override_survives_pen_reassignment_across_renders():
    """
    Simulates the real scenario the review flagged: the same style renders
    twice with different auto pen assignment (e.g. a different photo, or a
    re-ingest), producing different pass ids for the same role. A
    role-keyed override still finds its target in both renders.
    """
    render_a = LayeredSVG(
        width_mm=100,
        height_mm=100,
        passes=[make_pass("bands-navy", "Bands", "navy", [Polyline(points=[(0, 0), (1, 1)], pen_id="navy")], role="bands")],
    )
    render_b = LayeredSVG(
        width_mm=100,
        height_mm=100,
        passes=[make_pass("bands-teal", "Bands", "teal", [Polyline(points=[(0, 0), (1, 1)], pen_id="teal")], role="bands")],
    )
    pal = load_palette("default-6")
    override = {"bands": {"pen_id": "crimson"}}
    out_a = apply_pass_overrides(render_a, pal, override)
    out_b = apply_pass_overrides(render_b, pal, override)
    assert out_a.passes[0].pen_id == "crimson"
    assert out_b.passes[0].pen_id == "crimson"


def test_pass_override_ignores_invalid_pen_id():
    layered = _sample_layered()
    pal = load_palette("default-6")
    out = apply_pass_overrides(layered, pal, {"structure": {"pen_id": "not-a-real-pen"}})
    structure = next(p for p in out.passes if p.stable_role() == "structure")
    assert structure.pen_id == "black"


def test_pass_override_noop_when_no_overrides_given():
    layered = _sample_layered()
    pal = load_palette("default-6")
    out = apply_pass_overrides(layered, pal, None)
    assert out is layered


def test_pass_overrides_flow_through_render_job_params_extra():
    """
    End-to-end: params_extra["pass_overrides"] is a generic pipeline
    mechanism (not portrait-specific), reaching any style through the
    existing params_extra passthrough with no new API fields needed.
    """
    baseline_job, baseline_payload, baseline_layers = render_job(
        app="test", style_id="hatch", palette_id="default-6", seed=7, quality=QualityPreset.BOOTH_FAST
    )
    baseline_role = baseline_layers["passes"][0]["role"]

    job, payload, layers = render_job(
        app="test",
        style_id="hatch",
        palette_id="default-6",
        seed=7,
        quality=QualityPreset.BOOTH_FAST,
        params_extra={"pass_overrides": {baseline_role: {"pen_id": "teal"}}},
    )
    overridden = next(p for p in layers["passes"] if p["role"] == baseline_role)
    assert overridden["pen_id"] == "teal"
    assert baseline_role in (layers["meta"] or {}).get("pass_overrides_applied", [])
