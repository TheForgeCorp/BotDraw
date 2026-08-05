"""LettersBot layout, multilingual text, wedding corpus helpers."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from botdraw.core.models import (
    LayeredSVG,
    Orientation,
    PaperSize,
    PassLayer,
    Polyline,
    paper_dims,
)
from botdraw.core.overlays import OverlayPassComposer
from botdraw.core.svg import make_pass
from botdraw.letters.fonts import glyph_for, load_font
from botdraw.palettes import load_palette

CORPUS_PATH = Path(__file__).parent / "corpus" / "bollywood_motifs.json"

# Intentional missing-glyph mark (not a fake script character).
_MISSING_GLYPH = {
    "advance": 5.0,
    "strokes": [
        [(0.8, 1.2), (4.0, 1.2), (4.0, 8.8), (0.8, 8.8), (0.8, 1.2)],
        [(1.4, 2.0), (3.4, 7.8)],
    ],
}

# Hershey-like stroke digits for overlay text / quick layout checks.
HERSHEY_LIKE = {
    "0": [[(2, 0), (6, 0), (8, 2), (8, 8), (6, 10), (2, 10), (0, 8), (0, 2), (2, 0)]],
    "1": [[(3, 2), (5, 0), (5, 10)], [(3, 10), (7, 10)]],
    "2": [[(1, 2), (2, 0), (6, 0), (8, 2), (8, 4), (0, 10), (8, 10)]],
    "3": [[(1, 1), (4, 0), (7, 1), (7, 4), (4, 5), (7, 6), (7, 9), (4, 10), (1, 9)]],
    "4": [[(6, 0), (6, 10)], [(6, 0), (0, 6), (8, 6)]],
    "5": [[(7, 0), (1, 0), (1, 4), (6, 4), (8, 6), (7, 9), (4, 10), (1, 9)]],
    "6": [[(7, 1), (4, 0), (1, 2), (0, 5), (1, 8), (4, 10), (7, 8), (7, 6), (4, 5), (1, 6)]],
    "7": [[(1, 0), (8, 0), (3, 10)]],
    "8": [
        [(4, 5), (1, 4), (1, 1), (4, 0), (7, 1), (7, 4), (4, 5)],
        [(4, 5), (1, 6), (1, 9), (4, 10), (7, 9), (7, 6), (4, 5)],
    ],
    "9": [[(1, 9), (4, 10), (7, 8), (8, 5), (7, 2), (4, 0), (1, 2), (1, 4), (4, 5), (7, 4)]],
}


def _script_name(ch: str) -> str | None:
    if not ch or ch.isspace():
        return None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return "unknown"
    for key in (
        "DEVANAGARI",
        "GURMUKHI",
        "ARABIC",
        "CYRILLIC",
        "HIRAGANA",
        "KATAKANA",
        "CJK",
        "HEBREW",
        "THAI",
    ):
        if key in name:
            return key.lower()
    if ord(ch) > 127 and ch not in load_font()["glyphs"]:
        return "other"
    return None


def _chaikin(points: list[tuple[float, float]], iterations: int = 1) -> list[tuple[float, float]]:
    pts = points
    for _ in range(iterations):
        if len(pts) < 2:
            return pts
        nxt: list[tuple[float, float]] = [pts[0]]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            nxt.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            nxt.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        nxt.append(pts[-1])
        pts = nxt
    return pts


def _humanize_stroke(
    pts: list[tuple[float, float]],
    *,
    amount: float,
    rng: np.random.Generator,
    baseline: float,
) -> list[tuple[float, float]]:
    """Stroke-level humanize: mild slant + baseline drift + low path noise."""
    if amount <= 0 or len(pts) < 2:
        return pts
    slant = rng.normal(0, 0.04 * amount)
    drift = rng.normal(0, 0.12 * amount)
    out: list[tuple[float, float]] = []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        # Correlated noise along the stroke (not independent per-vertex chaos).
        nx = rng.normal(0, 0.08 * amount)
        ny = rng.normal(0, 0.08 * amount)
        yy = y - baseline
        out.append((x + slant * yy + nx, y + drift + ny * (0.6 + 0.4 * t)))
    return out


def _clamp_line_angle(deg: float) -> float:
    # Quantize to 0.05° and clamp to ±0.5°.
    stepped = round(float(deg) / 0.05) * 0.05
    return float(max(-0.5, min(0.5, stepped)))


def _rotate_point(
    px: float, py: float, *, ox: float, oy: float, angle_rad: float
) -> tuple[float, float]:
    if abs(angle_rad) < 1e-12:
        return px, py
    c, s = float(np.cos(angle_rad)), float(np.sin(angle_rad))
    dx, dy = px - ox, py - oy
    return ox + dx * c - dy * s, oy + dx * s + dy * c


def layout_text(
    text: str,
    *,
    x: float,
    y: float,
    size_mm: float = 4.5,
    line_height: float | None = None,
    tracking: float = 0.0,
    max_width: float = 160.0,
    pen_id: str = "ink",
    humanize: float = 0.08,
    seed: int = 1,
    font_name: str = "simplex",
    leading_variation: float = 0.0,
    line_angle_deg: float = 0.0,
) -> tuple[list[Polyline], list[dict], dict]:
    """Return polylines, per-word spans (with text), and layout meta."""
    font = load_font(font_name)
    rng = np.random.default_rng(seed)
    scale = size_mm / float(font.get("em_size", 10.0))
    leading = line_height if line_height is not None else size_mm * 1.55
    v = float(max(0.0, min(1.0, leading_variation)))
    angle_deg = _clamp_line_angle(line_angle_deg)
    angle_rad = float(np.deg2rad(angle_deg))
    cx, cy = x, y
    line_origin_x, line_origin_y = x, y
    polys: list[Polyline] = []
    spans: list[dict] = []
    missing_scripts: set[str] = set()
    word_start_x = cx
    word_chars: list[str] = []

    def next_leading() -> float:
        if v <= 0:
            return leading
        factor = 1.0 + float(rng.uniform(-v, v)) * 0.35
        return max(leading * 0.7, leading * factor)

    def advance_line():
        nonlocal cx, cy, word_start_x, line_origin_x, line_origin_y
        cx = x
        cy += next_leading()
        line_origin_x, line_origin_y = x, cy
        word_start_x = cx

    def flush_word(end_x: float, baseline: float):
        nonlocal word_start_x, word_chars
        if word_chars:
            x0, y0 = word_start_x, baseline
            x1, y1 = end_x, baseline + size_mm
            corners = [
                _rotate_point(x0, y0, ox=line_origin_x, oy=line_origin_y, angle_rad=angle_rad),
                _rotate_point(x1, y0, ox=line_origin_x, oy=line_origin_y, angle_rad=angle_rad),
                _rotate_point(x1, y1, ox=line_origin_x, oy=line_origin_y, angle_rad=angle_rad),
                _rotate_point(x0, y1, ox=line_origin_x, oy=line_origin_y, angle_rad=angle_rad),
            ]
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            spans.append(
                {
                    "x": min(xs),
                    "y": min(ys),
                    "w": max(2.0, max(xs) - min(xs)),
                    "h": max(size_mm * 0.5, max(ys) - min(ys)),
                    "text": "".join(word_chars),
                    "baseline_y": _rotate_point(
                        word_start_x, baseline, ox=line_origin_x, oy=line_origin_y, angle_rad=angle_rad
                    )[1],
                    "x0": corners[0][0],
                    "y0": corners[0][1],
                    "x1": corners[1][0],
                    "y1": corners[1][1],
                }
            )
        word_chars = []

    def advance_for(ch: str, glyph: dict) -> float:
        return (glyph["advance"] + tracking) * scale

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            flush_word(cx, cy)
            advance_line()
            i += 1
            continue
        if ch == " ":
            flush_word(cx, cy)
            space = glyph_for(" ", font) or {"advance": 3.2, "strokes": []}
            cx += advance_for(" ", space)
            word_start_x = cx
            i += 1
            continue

        if not word_chars:
            j = i
            word_w = 0.0
            while j < len(text) and text[j] not in " \n":
                g = glyph_for(text[j], font)
                if g is None:
                    script = _script_name(text[j])
                    if script:
                        missing_scripts.add(script)
                    g = _MISSING_GLYPH
                word_w += advance_for(text[j], g)
                j += 1
            if cx > x and (cx - x) + word_w > max_width:
                flush_word(cx, cy)
                advance_line()

        glyph = glyph_for(ch, font)
        if glyph is None:
            script = _script_name(ch)
            if script:
                missing_scripts.add(script)
            glyph = _MISSING_GLYPH

        for stroke in glyph["strokes"]:
            pts_u = [(float(px), float(py)) for px, py in stroke]
            if len(pts_u) >= 4:
                pts_u = _chaikin(pts_u, iterations=1)
            pts = [(cx + px * scale, cy + py * scale) for px, py in pts_u]
            pts = _humanize_stroke(pts, amount=humanize, rng=rng, baseline=cy + size_mm)
            if abs(angle_rad) > 1e-12:
                pts = [
                    _rotate_point(px, py, ox=line_origin_x, oy=line_origin_y, angle_rad=angle_rad)
                    for px, py in pts
                ]
            if len(pts) >= 2:
                polys.append(Polyline(points=pts, pen_id=pen_id))

        cx += advance_for(ch, glyph)
        word_chars.append(ch)
        i += 1

    flush_word(cx, cy)
    meta = {
        "font": font_name,
        "missing_scripts": sorted(missing_scripts),
        "glyph_count": sum(1 for c in text if not c.isspace()),
        "leading_variation": v,
        "line_angle_deg": angle_deg,
    }
    return polys, spans, meta


def _pick_highlight_spans(spans: list[dict], highlight_words: list[str] | None) -> list[dict]:
    if not spans:
        return []
    if highlight_words:
        keys = {w.strip().lower() for w in highlight_words if w and w.strip()}
        matched = [s for s in spans if s.get("text", "").lower().strip(".,!?;:\"'") in keys]
        if matched:
            return matched
        # Partial contains match
        matched = [
            s
            for s in spans
            if any(k in s.get("text", "").lower() for k in keys)
        ]
        if matched:
            return matched
        return []
    # Default emphasis: prefer meaningful words over short ones
    stop = {"a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are", "we", "our"}
    candidates = [s for s in spans if s.get("text", "").lower() not in stop and len(s.get("text", "")) > 3]
    pool = candidates or spans
    mid = len(pool) // 2
    return pool[mid : mid + 1]


@dataclass
class Margins:
    left: float = 18.0
    top: float = 18.0
    right: float = 18.0
    bottom: float = 18.0


@dataclass
class LineGeom:
    x0_mm: float = 20.0
    y0_mm: float = 40.0
    x1_mm: float = 120.0
    y1_mm: float = 40.0
    style: str = "solid"  # solid | dashed
    dash_mm: float = 2.0
    gap_mm: float = 1.2
    width_mm: float | None = None


@dataclass
class SnapSpec:
    target_layer_id: str | None = None
    span_index: int | None = None
    role: str = "underline"  # underline | highlight


@dataclass
class LetterLayerSpec:
    """One letter layer: text pass or geometric line pass."""

    id: str = "layer-0"
    name: str = "Ink"
    body: str = ""
    font_name: str = "simplex"
    size_mm: float = 4.5
    pen_id: str = "ink"
    language: str = "en"
    translate_from_en: bool = False
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    kind: str = "ink"  # ink | highlight | accent | underline
    tracking: float = 0.15
    humanize: float = 0.08
    line_height: float | None = None
    highlight_words: list[str] = field(default_factory=list)
    draw_mode: str = "text"  # text | line
    leading_variation: float = 0.12
    line_angle_deg: float = 0.0
    line: LineGeom = field(default_factory=LineGeom)
    placement: str = "freehand"  # freehand | snap
    snap: SnapSpec = field(default_factory=SnapSpec)


def _dashed_segments(
    x0: float, y0: float, x1: float, y1: float, *, dash_mm: float, gap_mm: float
) -> list[list[tuple[float, float]]]:
    dx, dy = x1 - x0, y1 - y0
    length = float(np.hypot(dx, dy))
    if length < 1e-6:
        return [[(x0, y0), (x1, y1)]]
    ux, uy = dx / length, dy / length
    dash = max(0.2, float(dash_mm))
    gap = max(0.1, float(gap_mm))
    segs: list[list[tuple[float, float]]] = []
    t = 0.0
    drawing = True
    while t < length - 1e-9:
        step = dash if drawing else gap
        t2 = min(length, t + step)
        if drawing:
            segs.append([(x0 + ux * t, y0 + uy * t), (x0 + ux * t2, y0 + uy * t2)])
        t = t2
        drawing = not drawing
    return segs or [[(x0, y0), (x1, y1)]]


def _snap_line_from_span(span: dict, role: str) -> tuple[float, float, float, float]:
    """Return x0,y0,x1,y1 from a word span."""
    if all(k in span for k in ("x0", "y0", "x1", "y1")):
        x0, y0, x1, y1 = span["x0"], span["y0"], span["x1"], span["y1"]
    else:
        x0 = float(span["x"])
        y0 = float(span.get("baseline_y", span["y"] + span.get("h", 4) * 0.85))
        x1 = x0 + float(span["w"])
        y1 = y0
    if role == "highlight":
        mid_y = float(span["y"]) + float(span.get("h", 4.0)) * 0.55
        return x0 - 0.4, mid_y, x1 + 0.4, mid_y
    # underline: slightly below baseline
    uy = float(span.get("baseline_y", y0)) + float(span.get("h", 4.0)) * 0.12
    return x0, uy, x1, uy


def _line_polylines(layer: LetterLayerSpec, pen_id: str) -> list[Polyline]:
    g = layer.line or LineGeom()
    x0, y0, x1, y1 = g.x0_mm, g.y0_mm, g.x1_mm, g.y1_mm
    if (g.style or "solid") == "dashed":
        chunks = _dashed_segments(x0, y0, x1, y1, dash_mm=g.dash_mm, gap_mm=g.gap_mm)
        return [Polyline(points=pts, pen_id=pen_id) for pts in chunks if len(pts) >= 2]
    return [Polyline(points=[(x0, y0), (x1, y1)], pen_id=pen_id)]


def render_letter_layers(
    layers: list[LetterLayerSpec],
    *,
    palette_id: str = "wedding-highlight",
    paper: PaperSize = PaperSize.A5,
    orientation: Orientation | str = "portrait",
    margins: Margins | None = None,
    seed: int = 7,
    guest_quote: str | None = None,
) -> LayeredSVG:
    """Compose text-pass and line layers into one LayeredSVG."""
    margins = margins or Margins()
    palette = load_palette(palette_id)
    orient_enum = (
        Orientation.LANDSCAPE
        if str(getattr(orientation, "value", orientation)).lower() == "landscape"
        else Orientation.PORTRAIT
    )
    pw, ph = paper_dims(paper, orient_enum)

    max_width = max(10.0, pw - margins.left - margins.right)
    passes: list[PassLayer] = []
    missing_scripts: set[str] = set()
    translate_pending = False
    layer_meta: list[dict[str, Any]] = []
    layer_spans: dict[str, list[dict]] = {}
    # First pass: layout all text layers so snap can resolve spans.
    text_layouts: dict[str, tuple[list[Polyline], list[dict], dict, Any]] = {}

    for idx, layer in enumerate(layers):
        try:
            pen = palette.pen_by_id(layer.pen_id)
        except KeyError:
            pen = palette.pens[0]
        lang = (layer.language or "en").lower()
        if lang not in {"en", "english"} and layer.translate_from_en:
            translate_pending = True

        draw_mode = (layer.draw_mode or "text").lower()
        lid = layer.id or f"layer-{idx}"
        if draw_mode == "line":
            continue

        text = (layer.body or "").strip()
        if idx == 0 and guest_quote and guest_quote not in text:
            text = f'{text}\n\n"{guest_quote}"' if text else f'"{guest_quote}"'
        x = margins.left + layer.offset_x_mm
        y = margins.top + 4.0 + layer.offset_y_mm
        polys, spans, layout_meta = layout_text(
            text,
            x=x,
            y=y,
            pen_id=pen.id,
            seed=seed + idx * 17,
            max_width=max_width,
            size_mm=layer.size_mm,
            line_height=layer.line_height,
            tracking=layer.tracking,
            humanize=layer.humanize,
            font_name=layer.font_name or "simplex",
            leading_variation=layer.leading_variation,
            line_angle_deg=layer.line_angle_deg,
        )
        missing_scripts.update(layout_meta.get("missing_scripts") or [])
        text_layouts[lid] = (polys, spans, layout_meta, pen)
        layer_spans[lid] = spans

    for idx, layer in enumerate(layers):
        try:
            pen = palette.pen_by_id(layer.pen_id)
        except KeyError:
            pen = palette.pens[0]
        lang = (layer.language or "en").lower()
        draw_mode = (layer.draw_mode or "text").lower()
        kind = layer.kind or "ink"
        lid = layer.id or f"layer-{idx}"

        if draw_mode == "line":
            g = layer.line or LineGeom()
            if (layer.placement or "freehand") == "snap" and layer.snap:
                tid = layer.snap.target_layer_id
                sidx = layer.snap.span_index
                spans = layer_spans.get(tid or "", [])
                if spans and sidx is not None and 0 <= int(sidx) < len(spans):
                    x0, y0, x1, y1 = _snap_line_from_span(spans[int(sidx)], layer.snap.role or "underline")
                    g = LineGeom(
                        x0_mm=x0,
                        y0_mm=y0,
                        x1_mm=x1,
                        y1_mm=y1,
                        style=g.style,
                        dash_mm=g.dash_mm,
                        gap_mm=g.gap_mm,
                        width_mm=g.width_mm,
                    )
                    layer.line = g
            # Mutate a temp layer copy for polyline build
            tmp = LetterLayerSpec(
                id=lid,
                name=layer.name,
                pen_id=pen.id,
                kind=kind,
                draw_mode="line",
                line=g,
            )
            polys = _line_polylines(tmp, pen.id)
            pass_kind = kind if kind in {"highlight", "underline", "accent"} else "accent"
            opacity = pen.profile.opacity
            if pass_kind == "highlight":
                opacity = pen.profile.opacity
            passes.append(
                make_pass(
                    lid,
                    layer.name or f"Line {idx + 1}",
                    pen.id,
                    polys,
                    kind=pass_kind,
                    opacity_override=opacity,
                )
            )
            layer_meta.append(
                {
                    "id": lid,
                    "name": layer.name,
                    "draw_mode": "line",
                    "pen_id": pen.id,
                    "board_id": pen.resolved_board_id(),
                    "kind": pass_kind,
                    "placement": layer.placement,
                    "line": {
                        "x0_mm": g.x0_mm,
                        "y0_mm": g.y0_mm,
                        "x1_mm": g.x1_mm,
                        "y1_mm": g.y1_mm,
                        "style": g.style,
                        "dash_mm": g.dash_mm,
                        "gap_mm": g.gap_mm,
                        "width_mm": g.width_mm,
                    },
                    "snap": {
                        "target_layer_id": layer.snap.target_layer_id if layer.snap else None,
                        "span_index": layer.snap.span_index if layer.snap else None,
                        "role": layer.snap.role if layer.snap else "underline",
                    },
                }
            )
            continue

        polys, spans, layout_meta, _pen = text_layouts.get(lid, ([], [], {}, pen))
        # Prefer layout pen id from layout polys
        if kind == "highlight" or pen.profile.nib_type.value == "highlighter":
            words = layer.highlight_words or None
            chosen = _pick_highlight_spans(spans, words) if spans else []
            if chosen:
                composer = OverlayPassComposer()
                tmp = LayeredSVG(width_mm=pw, height_mm=ph, passes=[], seed=seed)
                width = pen.profile.width_mm or 3.2
                tmp = composer.highlight_spans(
                    tmp, chosen, pen_id=pen.id, pad_mm=0.4, stroke_width_mm=width
                )
                if tmp.passes:
                    hl = tmp.passes[-1]
                    hl.id = lid
                    hl.name = layer.name or "Highlight"
                    hl.kind = "highlight"
                    passes.append(hl)
                else:
                    passes.append(
                        make_pass(lid, layer.name or f"Layer {idx + 1}", pen.id, polys, kind="highlight",
                                  opacity_override=pen.profile.opacity)
                    )
            else:
                passes.append(
                    make_pass(
                        lid,
                        layer.name or f"Layer {idx + 1}",
                        pen.id,
                        polys,
                        kind="highlight",
                        opacity_override=pen.profile.opacity,
                    )
                )
        else:
            passes.append(
                make_pass(lid, layer.name or f"Layer {idx + 1}", pen.id, polys, kind=kind)
            )

        layer_meta.append(
            {
                "id": lid,
                "name": layer.name,
                "draw_mode": "text",
                "font_name": layer.font_name,
                "size_mm": layer.size_mm,
                "pen_id": pen.id,
                "board_id": pen.resolved_board_id(),
                "language": lang,
                "translate_from_en": layer.translate_from_en,
                "offset_x_mm": layer.offset_x_mm,
                "offset_y_mm": layer.offset_y_mm,
                "kind": kind,
                "leading_variation": layer.leading_variation,
                "line_angle_deg": layer.line_angle_deg,
                "span_count": len(spans),
            }
        )

    rtl = any((L.language or "").lower() in {"ur", "urdu"} for L in layers)
    return LayeredSVG(
        width_mm=pw,
        height_mm=ph,
        passes=passes,
        seed=seed,
        meta={
            "margins": {
                "left": margins.left,
                "top": margins.top,
                "right": margins.right,
                "bottom": margins.bottom,
            },
            "layers": layer_meta,
            "layer_spans": layer_spans,
            "missing_scripts": sorted(missing_scripts),
            "translate_pending": translate_pending,
            "rtl": rtl,
            "urdu_fallback": "naskh-or-block" if rtl else None,
        },
    )


def render_letter(
    body: str,
    *,
    palette_id: str = "wedding-highlight",
    paper: PaperSize = PaperSize.A5,
    orientation: Orientation | str = Orientation.PORTRAIT,
    language: str = "en",
    highlight_words: list[str] | None = None,
    guest_quote: str | None = None,
    seed: int = 7,
    size_mm: float = 4.5,
    line_height: float | None = None,
    tracking: float = 0.15,
    humanize: float = 0.08,
    font_name: str = "simplex",
    margin_mm: float = 18.0,
    margins: Margins | None = None,
    pen_id: str | None = None,
) -> LayeredSVG:
    """Backward-compatible single-layer render."""
    if isinstance(orientation, Orientation):
        orient_s = orientation.value
    else:
        orient_s = str(orientation or "portrait")
    palette = load_palette(palette_id)
    ink = next((p for p in palette.pens if p.profile.nib_type.value != "highlighter"), palette.pens[0])
    high = next((p for p in palette.pens if p.profile.nib_type.value == "highlighter"), None)
    m = margins or Margins(left=margin_mm, top=margin_mm, right=margin_mm, bottom=margin_mm)
    layers = [
        LetterLayerSpec(
            id="letter-ink",
            name="Letter ink",
            body=body,
            font_name=font_name,
            size_mm=size_mm,
            pen_id=pen_id or ink.id,
            language=language,
            tracking=tracking,
            humanize=humanize,
            line_height=line_height,
            kind="ink",
        )
    ]
    layered = render_letter_layers(
        layers,
        palette_id=palette_id,
        paper=paper,
        orientation=orient_s,
        margins=m,
        seed=seed,
        guest_quote=guest_quote,
    )
    # Legacy: optional highlight pass when highlight_words provided (non-empty) or None (default mid).
    if high and highlight_words is not None:
        if highlight_words:
            # Re-layout spans for highlight from first ink pass body
            text = body.strip()
            if guest_quote:
                text = f'{text}\n\n"{guest_quote}"'
            _, spans, _ = layout_text(
                text,
                x=m.left,
                y=m.top + 4,
                pen_id=ink.id,
                seed=seed,
                max_width=max(10.0, layered.width_mm - m.left - m.right),
                size_mm=size_mm,
                tracking=tracking,
                humanize=0,
                font_name=font_name,
            )
            chosen = _pick_highlight_spans(spans, highlight_words)
            if chosen:
                composer = OverlayPassComposer()
                layered = composer.highlight_spans(
                    layered, chosen, pen_id=high.id, pad_mm=0.4, stroke_width_mm=high.profile.width_mm or 3.2
                )
    elif high and highlight_words is None:
        text = body.strip()
        if guest_quote:
            text = f'{text}\n\n"{guest_quote}"'
        _, spans, _ = layout_text(
            text,
            x=m.left,
            y=m.top + 4,
            pen_id=ink.id,
            seed=seed,
            max_width=max(10.0, layered.width_mm - m.left - m.right),
            size_mm=size_mm,
            tracking=tracking,
            humanize=0,
            font_name=font_name,
        )
        chosen = _pick_highlight_spans(spans, None)
        if chosen:
            composer = OverlayPassComposer()
            layered = composer.highlight_spans(
                layered, chosen, pen_id=high.id, pad_mm=0.4, stroke_width_mm=high.profile.width_mm or 3.2
            )
    return layered


def load_bollywood_corpus() -> list[dict]:
    import json

    if not CORPUS_PATH.exists():
        return []
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def motifs_for_era(era: str | None = None, mood: str | None = None) -> list[dict]:
    items = load_bollywood_corpus()
    out = items
    if era:
        out = [m for m in out if m.get("era") == era]
    if mood:
        out = [m for m in out if mood in m.get("moods", [])]
    return out or items
