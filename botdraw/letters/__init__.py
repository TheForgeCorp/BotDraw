"""LettersBot layout, multilingual text, wedding corpus helpers."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from botdraw.core.models import LayeredSVG, PAPER_MM, PaperSize, PassLayer, Polyline
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
) -> tuple[list[Polyline], list[dict], dict]:
    """Return polylines, per-word spans (with text), and layout meta."""
    font = load_font(font_name)
    rng = np.random.default_rng(seed)
    scale = size_mm / float(font.get("em_size", 10.0))
    leading = line_height if line_height is not None else size_mm * 1.55
    cx, cy = x, y
    polys: list[Polyline] = []
    spans: list[dict] = []
    missing_scripts: set[str] = set()
    word_start_x = cx
    word_chars: list[str] = []

    def flush_word(end_x: float, baseline: float):
        nonlocal word_start_x, word_chars
        if word_chars:
            spans.append(
                {
                    "x": word_start_x,
                    "y": baseline,
                    "w": max(2.0, end_x - word_start_x),
                    "h": size_mm,
                    "text": "".join(word_chars),
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
            cx = x
            cy += leading
            word_start_x = cx
            i += 1
            continue
        if ch == " ":
            flush_word(cx, cy)
            space = glyph_for(" ", font) or {"advance": 3.2, "strokes": []}
            cx += advance_for(" ", space)
            word_start_x = cx
            i += 1
            continue

        # Word-boundary wrap: measure upcoming word width
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
                cx = x
                cy += leading
                word_start_x = cx

        glyph = glyph_for(ch, font)
        if glyph is None:
            script = _script_name(ch)
            if script:
                missing_scripts.add(script)
            glyph = _MISSING_GLYPH

        for stroke in glyph["strokes"]:
            # Optional light smoothing for short polygonal arcs
            pts_u = [(float(px), float(py)) for px, py in stroke]
            if len(pts_u) >= 4:
                pts_u = _chaikin(pts_u, iterations=1)
            pts = [(cx + px * scale, cy + py * scale) for px, py in pts_u]
            pts = _humanize_stroke(pts, amount=humanize, rng=rng, baseline=cy + size_mm)
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
class LetterLayerSpec:
    """One text pass on the letter (own body, font, pen, language, offset)."""

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
    kind: str = "ink"  # ink | highlight | accent
    tracking: float = 0.15
    humanize: float = 0.08
    line_height: float | None = None
    highlight_words: list[str] = field(default_factory=list)


def render_letter_layers(
    layers: list[LetterLayerSpec],
    *,
    palette_id: str = "wedding-highlight",
    paper: PaperSize = PaperSize.A5,
    orientation: str = "portrait",
    margins: Margins | None = None,
    seed: int = 7,
    guest_quote: str | None = None,
) -> LayeredSVG:
    """Compose multiple text-pass layers into one LayeredSVG."""
    margins = margins or Margins()
    palette = load_palette(palette_id)
    pw, ph = PAPER_MM[paper]
    if orientation.lower() == "landscape":
        pw, ph = ph, pw

    max_width = max(10.0, pw - margins.left - margins.right)
    passes: list[PassLayer] = []
    missing_scripts: set[str] = set()
    translate_pending = False
    layer_meta: list[dict[str, Any]] = []

    for idx, layer in enumerate(layers):
        text = (layer.body or "").strip()
        if idx == 0 and guest_quote and guest_quote not in text:
            text = f'{text}\n\n"{guest_quote}"' if text else f'"{guest_quote}"'
        lang = (layer.language or "en").lower()
        if lang not in {"en", "english"} and layer.translate_from_en:
            # Stub: do not translate yet; flag for UI/settings.
            translate_pending = True
        try:
            pen = palette.pen_by_id(layer.pen_id)
        except KeyError:
            pen = palette.pens[0]

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
        )
        missing_scripts.update(layout_meta.get("missing_scripts") or [])

        kind = layer.kind or "ink"
        if kind == "highlight" or pen.profile.nib_type.value == "highlighter":
            # Highlighter: band over word spans (offset usually 0).
            words = layer.highlight_words or None
            chosen = _pick_highlight_spans(spans, words) if spans else []
            if chosen:
                composer = OverlayPassComposer()
                # Build a temp layered to reuse highlight helper, then extract pass.
                tmp = LayeredSVG(width_mm=pw, height_mm=ph, passes=[], seed=seed)
                width = pen.profile.width_mm or 3.2
                tmp = composer.highlight_spans(
                    tmp, chosen, pen_id=pen.id, pad_mm=0.4, stroke_width_mm=width
                )
                if tmp.passes:
                    hl = tmp.passes[-1]
                    hl.id = layer.id or f"layer-{idx}"
                    hl.name = layer.name or "Highlight"
                    hl.kind = "highlight"
                    passes.append(hl)
            else:
                # Fallback: draw text strokes with highlighter pen
                passes.append(
                    make_pass(
                        layer.id or f"layer-{idx}",
                        layer.name or f"Layer {idx + 1}",
                        pen.id,
                        polys,
                        kind="highlight",
                        opacity_override=pen.profile.opacity,
                    )
                )
        else:
            passes.append(
                make_pass(
                    layer.id or f"layer-{idx}",
                    layer.name or f"Layer {idx + 1}",
                    pen.id,
                    polys,
                    kind=kind,
                )
            )

        layer_meta.append(
            {
                "id": layer.id,
                "name": layer.name,
                "font_name": layer.font_name,
                "size_mm": layer.size_mm,
                "pen_id": pen.id,
                "board_id": pen.resolved_board_id(),
                "language": lang,
                "translate_from_en": layer.translate_from_en,
                "offset_x_mm": layer.offset_x_mm,
                "offset_y_mm": layer.offset_y_mm,
                "kind": kind,
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
    language: str = "en",
    highlight_words: list[str] | None = None,
    guest_quote: str | None = None,
    seed: int = 7,
    size_mm: float = 4.5,
    line_height: float | None = None,
    tracking: float = 0.15,
    humanize: float = 0.08,
    font_name: str = "simplex",
    orientation: str = "portrait",
    margin_mm: float = 18.0,
    margins: Margins | None = None,
    pen_id: str | None = None,
) -> LayeredSVG:
    """Backward-compatible single-layer render."""
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
        orientation=orientation,
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
