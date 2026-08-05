"""LettersBot stroke-font quality + highlight behavior."""

from botdraw.letters import layout_text, render_letter
from botdraw.core.models import PaperSize


def test_hello_uses_metrics_and_lowercase():
    polys, spans, meta = layout_text("Hello", x=10, y=20, size_mm=5, humanize=0, seed=1)
    assert polys, "expected stroke polylines"
    assert meta["font"] == "simplex"
    assert spans and spans[0]["text"] == "Hello"
    # Variable advances: word width should be less than monospace 5 glyphs * ~size
    assert spans[0]["w"] < 5 * 5.5


def test_humanize_seed_stable():
    a, _, _ = layout_text("PLOT", x=0, y=0, humanize=0.2, seed=99)
    b, _, _ = layout_text("PLOT", x=0, y=0, humanize=0.2, seed=99)
    assert [p.points for p in a] == [p.points for p in b]


def test_highlight_matches_keywords():
    layered = render_letter(
        "We promise forever together",
        highlight_words=["forever"],
        humanize=0,
        seed=1,
    )
    kinds = [p.kind for p in layered.passes]
    assert "ink" in kinds or any(p.id.startswith("letter-ink") or p.kind == "ink" for p in layered.passes)
    assert any(p.kind == "highlight" for p in layered.passes)


def test_highlight_off_no_pass():
    layered = render_letter("HELLO WORLD", highlight_words=[], humanize=0, seed=1)
    assert all(p.kind != "highlight" for p in layered.passes)


def test_missing_script_meta():
    layered = render_letter("नमस्ते", highlight_words=[], humanize=0, seed=1, language="hi")
    assert "devanagari" in layered.meta.get("missing_scripts", [])


def test_landscape_swaps_paper():
    port = render_letter("Hi", paper=PaperSize.A5, orientation="portrait", highlight_words=[], humanize=0)
    land = render_letter("Hi", paper=PaperSize.A5, orientation="landscape", highlight_words=[], humanize=0)
    assert port.width_mm < port.height_mm
    assert land.width_mm > land.height_mm
