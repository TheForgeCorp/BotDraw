"""LettersBot layout, multilingual text, wedding corpus helpers."""

from __future__ import annotations

from pathlib import Path

from botdraw.core.models import LayeredSVG, PAPER_MM, PaperSize, Polyline, StyleParams
from botdraw.core.overlays import OverlayPassComposer
from botdraw.core.svg import make_pass
from botdraw.palettes import load_palette

CORPUS_PATH = Path(__file__).parent / "corpus" / "bollywood_motifs.json"

# Simple stroke-font approximations for Latin + placeholder boxes for complex scripts
HERSHEY_LIKE = {
    "A": [[(0, 10), (5, 0), (10, 10)], [(2.5, 5), (7.5, 5)]],
    "B": [[(0, 0), (0, 10), (7, 10), (8, 8), (7, 5), (0, 5)], [(0, 5), (7, 5), (8, 3), (7, 0), (0, 0)]],
    "C": [[(8, 1), (4, 0), (1, 2), (0, 5), (1, 8), (4, 10), (8, 9)]],
    "D": [[(0, 0), (0, 10), (6, 10), (9, 7), (9, 3), (6, 0), (0, 0)]],
    "E": [[(8, 0), (0, 0), (0, 10), (8, 10)], [(0, 5), (6, 5)]],
    "F": [[(0, 10), (0, 0), (8, 0)], [(0, 5), (6, 5)]],
    "G": [[(8, 2), (5, 0), (1, 2), (0, 5), (1, 8), (5, 10), (8, 8), (8, 5), (5, 5)]],
    "H": [[(0, 0), (0, 10)], [(8, 0), (8, 10)], [(0, 5), (8, 5)]],
    "I": [[(2, 0), (6, 0)], [(4, 0), (4, 10)], [(2, 10), (6, 10)]],
    "J": [[(6, 0), (6, 8), (4, 10), (1, 8)]],
    "K": [[(0, 0), (0, 10)], [(7, 0), (0, 5), (7, 10)]],
    "L": [[(0, 0), (0, 10), (7, 10)]],
    "M": [[(0, 10), (0, 0), (4, 5), (8, 0), (8, 10)]],
    "N": [[(0, 10), (0, 0), (8, 10), (8, 0)]],
    "O": [[(2, 0), (6, 0), (8, 2), (8, 8), (6, 10), (2, 10), (0, 8), (0, 2), (2, 0)]],
    "P": [[(0, 10), (0, 0), (6, 0), (8, 2), (6, 5), (0, 5)]],
    "Q": [[(2, 0), (6, 0), (8, 2), (8, 8), (6, 10), (2, 10), (0, 8), (0, 2), (2, 0)], [(5, 7), (8, 10)]],
    "R": [[(0, 10), (0, 0), (6, 0), (8, 2), (6, 5), (0, 5)], [(3, 5), (8, 10)]],
    "S": [[(7, 1), (4, 0), (1, 2), (2, 4), (6, 6), (7, 8), (4, 10), (1, 9)]],
    "T": [[(0, 0), (8, 0)], [(4, 0), (4, 10)]],
    "U": [[(0, 0), (0, 8), (2, 10), (6, 10), (8, 8), (8, 0)]],
    "V": [[(0, 0), (4, 10), (8, 0)]],
    "W": [[(0, 0), (2, 10), (4, 4), (6, 10), (8, 0)]],
    "X": [[(0, 0), (8, 10)], [(8, 0), (0, 10)]],
    "Y": [[(0, 0), (4, 5), (8, 0)], [(4, 5), (4, 10)]],
    "Z": [[(0, 0), (8, 0), (0, 10), (8, 10)]],
    " ": [],
    ".": [[(4, 9), (4.2, 9.2)]],
    ",": [[(4, 9), (3, 11)]],
    "!": [[(4, 0), (4, 7)], [(4, 9), (4.2, 9.2)]],
    "?": [[(1, 2), (2, 0), (6, 0), (7, 2), (4, 5), (4, 7)], [(4, 9), (4.2, 9.2)]],
    "'": [[(4, 0), (4, 2)]],
    "-": [[(2, 5), (6, 5)]],
}


def _glyph_strokes(ch: str) -> list[list[tuple[float, float]]]:
    up = ch.upper()
    if up in HERSHEY_LIKE:
        return HERSHEY_LIKE[up]
    # Non-Latin: draw a characteristic underline + tick so layout still works
    return [[(0, 8), (8, 8)], [(2, 2), (6, 6)]]


def layout_text(
    text: str,
    *,
    x: float,
    y: float,
    size_mm: float = 4.5,
    line_height: float = 7.0,
    max_width: float = 160.0,
    pen_id: str = "ink",
    humanize: float = 0.15,
    seed: int = 1,
) -> tuple[list[Polyline], list[dict]]:
    """Return polylines and per-word span boxes for highlighting."""
    import numpy as np

    rng = np.random.default_rng(seed)
    scale = size_mm / 10.0
    cx, cy = x, y
    polys: list[Polyline] = []
    spans: list[dict] = []
    word_start_x = cx
    word_chars = 0

    def flush_word(end_x: float, baseline: float):
        nonlocal word_start_x, word_chars
        if word_chars > 0:
            spans.append(
                {
                    "x": word_start_x,
                    "y": baseline,
                    "w": max(2.0, end_x - word_start_x),
                    "h": size_mm,
                    "text": "",
                }
            )
        word_chars = 0

    for ch in text:
        if ch == "\n":
            flush_word(cx, cy)
            cx = x
            cy += line_height
            word_start_x = cx
            continue
        if ch == " ":
            flush_word(cx, cy)
            cx += 3 * scale
            word_start_x = cx
            continue
        if cx - x > max_width:
            flush_word(cx, cy)
            cx = x
            cy += line_height
            word_start_x = cx
        strokes = _glyph_strokes(ch)
        for stroke in strokes:
            pts = []
            for gx, gy in stroke:
                jx = rng.normal(0, humanize)
                jy = rng.normal(0, humanize)
                pts.append((cx + (gx + jx) * scale, cy + (gy + jy) * scale))
            if len(pts) >= 2:
                polys.append(Polyline(points=pts, pen_id=pen_id))
        cx += 9 * scale
        word_chars += 1
    flush_word(cx, cy)
    return polys, spans


def render_letter(
    body: str,
    *,
    palette_id: str = "wedding-highlight",
    paper: PaperSize = PaperSize.A5,
    language: str = "en",
    highlight_words: list[str] | None = None,
    guest_quote: str | None = None,
    seed: int = 7,
) -> LayeredSVG:
    palette = load_palette(palette_id)
    ink = next((p for p in palette.pens if p.profile.nib_type.value != "highlighter"), palette.pens[0])
    high = next((p for p in palette.pens if p.profile.nib_type.value == "highlighter"), None)
    pw, ph = PAPER_MM[paper]
    text = body.strip()
    if guest_quote:
        text = f'{text}\n\n"{guest_quote}"'
    # RTL marker for Urdu display note in meta; layout still LTR glyph placeholders
    rtl = language.lower() in {"ur", "urdu"}
    polys, spans = layout_text(text, x=18, y=22, pen_id=ink.id, seed=seed, max_width=pw - 36)
    layered = LayeredSVG(
        width_mm=pw,
        height_mm=ph,
        passes=[make_pass("letter-ink", "Letter ink", ink.id, polys)],
        seed=seed,
        meta={"language": language, "rtl": rtl, "urdu_fallback": "naskh-or-block" if rtl else None},
    )
    if high and highlight_words:
        # Highlight spans whose index matches keywords roughly: highlight first N spans
        chosen = spans[: min(len(spans), max(1, len(highlight_words)))]
        composer = OverlayPassComposer()
        layered = composer.highlight_spans(layered, chosen, pen_id=high.id)
    elif high and spans:
        # Highlight middle span as emphasis default
        mid = spans[len(spans) // 2 : len(spans) // 2 + 1]
        composer = OverlayPassComposer()
        layered = composer.highlight_spans(layered, mid, pen_id=high.id)
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
