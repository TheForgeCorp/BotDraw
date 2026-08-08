"""Auto + override pen assignment for PortraitVector."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from botdraw.core.models import LineProfile, NibType, PaletteSet, Pen
from botdraw.palettes import ink_pens
from botdraw.portrait.models import PortraitVector


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) < 6:
        return (0, 0, 0)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _saturation(hex_color: str) -> float:
    r, g, b = (v / 255.0 for v in _hex_to_rgb(hex_color))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx <= 1e-6 else (mx - mn) / mx


def photo_is_low_chroma(pv: PortraitVector, *, threshold: float = 0.12) -> bool:
    """
    True for black-and-white / desaturated photos.

    Cluster and hatch pen assignment otherwise pick the nearest-by-color
    palette pen with no floor on how saturated that pen is allowed to be —
    on a palette with no true gray (e.g. default-6: black plus navy,
    crimson, ochre, teal), a neutral gray photo tone gets mapped onto
    whichever saturated hue happens to be least-far away. That reads as an
    arbitrary color choice, not a deliberate one, and is why real B&W
    headshots were coming out navy/ochre/teal instead of monochrome.
    """
    rgb = np.asarray(pv.rgb, dtype=np.float32)
    if rgb.size == 0:
        return False
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return float(np.mean(sat)) < threshold


def _rgb_to_approx_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Cheap perceptual distance (sRGB → approx Lab-ish)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0

    def f(u: float) -> float:
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    r, g, b = f(r), f(g), f(b)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    return (y, x - z, y - (x + z) / 2)  # L-ish, a-ish, b-ish


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, aa, ba = _rgb_to_approx_lab(*a)
    lb, ab, bb = _rgb_to_approx_lab(*b)
    return (la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2


def apply_pen_overrides(palette: PaletteSet, overrides: dict[str, Any] | None) -> PaletteSet:
    """Return a shallow-copied palette with per-pen profile/color overrides for this job."""
    if not overrides:
        return palette
    pens: list[Pen] = []
    for pen in palette.pens:
        ov = overrides.get(pen.id) or {}
        if not ov:
            pens.append(pen)
            continue
        profile = pen.profile.model_copy()
        if "width_mm" in ov and ov["width_mm"] is not None:
            w = float(ov["width_mm"])
            profile.width_mm = w
            profile.min_width_mm = w * 0.8
            profile.max_width_mm = w * 1.2
        if "opacity" in ov and ov["opacity"] is not None:
            profile.opacity = float(ov["opacity"])
        if "nib_type" in ov and ov["nib_type"]:
            profile.nib_type = NibType(ov["nib_type"])
        pens.append(
            pen.model_copy(
                update={
                    "color_hex": ov.get("color_hex") or pen.color_hex,
                    "profile": profile,
                }
            )
        )
    return palette.model_copy(update={"pens": pens})


def assign_pens(
    pv: PortraitVector,
    palette: PaletteSet,
    *,
    pen_map: dict[str, str] | None = None,
) -> PortraitVector:
    """
    Auto-assign clusters/regions to ink pens (perceptual + one-to-one bias),
    then apply user pen_map overrides. Width-aware: edge → narrowest fineliner.
    """
    pens = ink_pens(palette)
    if not pens:
        pens = list(palette.pens)
    pen_by_id = {p.id: p for p in pens}

    # On a genuinely low-chroma (B&W) photo, restrict candidates to the
    # palette's own low-saturation pens so a neutral tone doesn't get
    # mapped onto an arbitrary saturated hue. Fall back to the full
    # palette only if it has no low-saturation pens at all to offer.
    monochrome_source = photo_is_low_chroma(pv)
    chroma_pens = [p for p in pens if _saturation(p.color_hex) < 0.25]
    tone_pens = chroma_pens if (monochrome_source and chroma_pens) else pens

    # Sort clusters by area desc
    clusters = sorted(pv.clusters, key=lambda c: -c.area)
    used: set[str] = set()
    auto_map: dict[str, str] = {}

    for cl in clusters:
        best = None
        best_d = float("inf")
        # Prefer unused pens first
        candidates = [p for p in tone_pens if p.id not in used] or tone_pens
        # Prefer wider markers for large colorful areas
        for p in candidates:
            pr, pg, pb = _hex_to_rgb(p.color_hex)
            d = _dist(cl.mean_rgb, (float(pr), float(pg), float(pb)))
            # Slight preference: large area + wide nib
            if cl.area > 500 and p.profile.width_mm >= 0.55:
                d *= 0.92
            if d < best_d:
                best_d = d
                best = p
        if best:
            auto_map[cl.id] = best.id
            used.add(best.id)
            cl.default_pen_id = best.id

    # Edge role: narrowest non-highlighter
    edge_pen = min(pens, key=lambda p: (p.profile.width_mm, 0 if p.profile.nib_type == NibType.FINELINER else 1))
    auto_map["edge"] = edge_pen.id
    # Hatch role: darkest near-black / warm gray — not a vivid accent
    def _lum(p) -> float:
        r, g, b = _hex_to_rgb(p.color_hex)
        return 0.299 * r + 0.587 * g + 0.114 * b

    dark = sorted(tone_pens, key=lambda p: (_lum(p), -p.profile.width_mm))
    hatch_pen = next((p for p in dark if p.id != edge_pen.id and _lum(p) < 80), None)
    if hatch_pen is None:
        if monochrome_source:
            # No second low-chroma pen to differentiate with — reuse the
            # edge pen rather than spilling into a saturated accent color
            # (the previous behavior, and the reason B&W photos always
            # hatched in whichever pen was "next darkest" — usually navy).
            hatch_pen = edge_pen
        else:
            wider = sorted(pens, key=lambda p: (p.profile.width_mm, p.id))
            hatch_pen = wider[min(1, len(wider) - 1)] if len(wider) > 1 else edge_pen
    auto_map["hatch"] = hatch_pen.id

    # Merge overrides
    final = dict(auto_map)
    if pen_map:
        for k, v in pen_map.items():
            if v in pen_by_id or any(p.id == v for p in palette.pens):
                final[k] = v

    # Stamp regions
    for r in pv.regions:
        pid = final.get(r.id) or final.get("edge")
        r.pen_id = pid

    pv.pen_map = final
    pv.meta = {
        **pv.meta,
        "monochrome_source": monochrome_source,
        "pen_assignment": [
            {
                "cluster_id": cid,
                "pen_id": pid,
                "color_hex": (pen_by_id.get(pid) or palette.pens[0]).color_hex,
                "width_mm": (pen_by_id.get(pid) or palette.pens[0]).profile.width_mm,
                "nib_type": (pen_by_id.get(pid) or palette.pens[0]).profile.nib_type.value,
            }
            for cid, pid in final.items()
        ],
    }
    return pv
