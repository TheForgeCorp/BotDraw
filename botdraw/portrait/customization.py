"""
Per-pass print customization: pen reassignment and visibility, keyed by a
pass's stable semantic *role* rather than its `id`.

Why role, not id: pass ids are frequently pen-derived (``hatch-{pen_id}``,
``bands-{pen_id}``, ``mosaic-{pen_id}``, ``midtone-{pen_id}``) so they shift
whenever auto pen assignment does. A user-saved "make the bands pass use
crimson" preference keyed by id breaks the moment a different photo (or a
re-render of the same one) assigns a different pen to that role. `role`
(``PassLayer.role``, falling back to `id` for passes created before the
field existed) stays constant across renders — see ``core/models.py``.

This intentionally does NOT yet cover per-pass linetype overrides: that
needs threading a per-role line_type dict through
``ornament.decorate_layered`` (today a single line_type applies to the
whole render, gated by ``ornament_target``), which is real additional work
tracked as a follow-up rather than half-implemented here.
"""
from __future__ import annotations

from typing import Any

from botdraw.core.models import LayeredSVG, PaletteSet


def describe_passes(layered: LayeredSVG) -> list[dict[str, Any]]:
    """One row per pass: stable role, current pen, display name — the shape
    a customization UI would list to build override controls against."""
    return [
        {
            "role": p.stable_role(),
            "id": p.id,
            "name": p.name,
            "pen_id": p.pen_id,
            "kind": p.kind,
            "polyline_count": len(p.polylines),
        }
        for p in layered.passes
    ]


def apply_pass_overrides(
    layered: LayeredSVG,
    palette: PaletteSet,
    overrides: dict[str, dict[str, Any]] | None,
) -> LayeredSVG:
    """
    Apply per-role overrides to a rendered LayeredSVG.

    ``overrides``: ``{role: {"pen_id": str | None, "visible": bool | None}}``.
    A role with no matching pass, or an invalid ``pen_id``, is ignored
    (fail-soft — same philosophy as ``pens.apply_pen_overrides``). Setting
    ``visible: false`` drops the pass entirely (it never reaches SVG/motion
    export, not just hidden in a preview toggle, unlike the Dev Panel
    Layers-panel solo/hide which only affects the canvas preview).
    """
    if not overrides:
        return layered
    valid_pen_ids = {p.id for p in palette.pens}
    applied: list[str] = []
    new_passes = []
    for p in layered.passes:
        ov = overrides.get(p.stable_role())
        if not ov:
            new_passes.append(p)
            continue
        if ov.get("visible") is False:
            applied.append(p.stable_role())
            continue
        pen_id = ov.get("pen_id")
        if pen_id and pen_id in valid_pen_ids and pen_id != p.pen_id:
            new_passes.append(
                p.model_copy(
                    update={
                        "pen_id": pen_id,
                        "polylines": [pl.model_copy(update={"pen_id": pen_id}) for pl in p.polylines],
                    }
                )
            )
            applied.append(p.stable_role())
        else:
            new_passes.append(p)

    meta = {**(layered.meta or {}), "pass_overrides_applied": applied}
    return layered.model_copy(update={"passes": new_passes, "meta": meta})
