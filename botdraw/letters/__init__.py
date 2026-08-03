"""LettersBot layout, multilingual text, wedding corpus helpers."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import numpy as np

from botdraw.core.models import LayeredSVG, PAPER_MM, PaperSize, Polyline
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
) -> LayeredSVG:
    palette = load_palette(palette_id)
    ink = next((p for p in palette.pens if p.profile.nib_type.value != "highlighter"), palette.pens[0])
    high = next((p for p in palette.pens if p.profile.nib_type.value == "highlighter"), None)
    pw, ph = PAPER_MM[paper]
    if orientation.lower() == "landscape":
        pw, ph = ph, pw
    text = body.strip()
    if guest_quote:
        text = f'{text}\n\n"{guest_quote}"'
    rtl = language.lower() in {"ur", "urdu"}
    polys, spans, layout_meta = layout_text(
        text,
        x=margin_mm,
        y=margin_mm + 4,
        pen_id=ink.id,
        seed=seed,
        max_width=pw - margin_mm * 2,
        size_mm=size_mm,
        line_height=line_height,
        tracking=tracking,
        humanize=humanize,
        font_name=font_name,
    )
    layered = LayeredSVG(
        width_mm=pw,
        height_mm=ph,
        passes=[make_pass("letter-ink", "Letter ink", ink.id, polys)],
        seed=seed,
        meta={
            "language": language,
            "rtl": rtl,
            "urdu_fallback": "naskh-or-block" if rtl else None,
            **layout_meta,
        },
    )
    if high and highlight_words is not None:
        # Explicit list (possibly empty): only highlight on non-empty keyword matches / default when None
        if highlight_words:
            chosen = _pick_highlight_spans(spans, highlight_words)
            if chosen:
                width = getattr(high.profile, "width_mm", 3.2) or 3.2
                composer = OverlayPassComposer()
                layered = composer.highlight_spans(
                    layered, chosen, pen_id=high.id, pad_mm=0.4, stroke_width_mm=width
                )
    elif high and highlight_words is None and spans:
        chosen = _pick_highlight_spans(spans, None)
        width = getattr(high.profile, "width_mm", 3.2) or 3.2
        composer = OverlayPassComposer()
        layered = composer.highlight_spans(
            layered, chosen, pen_id=high.id, pad_mm=0.4, stroke_width_mm=width
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
