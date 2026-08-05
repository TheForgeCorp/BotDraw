"""Letters multi-layer, margins, fonts, translate stub."""

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.letters import LetterLayerSpec, Margins, layout_text, render_letter_layers
from botdraw.letters.fonts import list_fonts, load_font
from botdraw.palettes import load_palette


client = TestClient(app)


def test_fonts_api_lists_stroke_faces():
    r = client.get("/api/letters/fonts")
    assert r.status_code == 200
    ids = {f["id"] for f in r.json()["fonts"]}
    assert "simplex" in ids
    assert "timesr" in ids
    assert "scripts" in ids


def test_list_fonts_and_load():
    fonts = list_fonts()
    assert len(fonts) >= 2
    f = load_font("timesr")
    assert "A" in f["glyphs"]


def test_pen_board_ids_on_palette():
    pal = load_palette("wedding-highlight")
    ink = pal.pen_by_id("ink")
    assert ink.board_id == "BD-INK-01"
    assert ink.resolved_board_id() == "BD-INK-01"


def test_margins_ltrb_shift_bounds():
    tight = Margins(left=10, top=10, right=10, bottom=10)
    wide = Margins(left=40, top=40, right=20, bottom=20)
    layers = [LetterLayerSpec(id="a", body="HELLO", pen_id="ink", size_mm=5, humanize=0)]
    a = render_letter_layers(layers, margins=tight, seed=1)
    b = render_letter_layers(layers, margins=wide, seed=1)
    ax = min(p for pl in a.passes[0].polylines for p, _ in pl.points)
    bx = min(p for pl in b.passes[0].polylines for p, _ in pl.points)
    assert bx > ax


def test_two_layers_with_offset():
    layers = [
        LetterLayerSpec(id="ink", name="Ink", body="HI", pen_id="ink", size_mm=5, humanize=0),
        LetterLayerSpec(
            id="shadow",
            name="Shadow",
            body="HI",
            pen_id="rose",
            size_mm=5,
            humanize=0,
            offset_x_mm=2.0,
            offset_y_mm=1.5,
            kind="accent",
        ),
    ]
    layered = render_letter_layers(layers, seed=2)
    assert len(layered.passes) == 2
    ax = min(p for pl in layered.passes[0].polylines for p, _ in pl.points)
    bx = min(p for pl in layered.passes[1].polylines for p, _ in pl.points)
    assert abs((bx - ax) - 2.0) < 0.2


def test_translate_stub_flags_pending():
    layers = [
        LetterLayerSpec(
            id="a",
            body="Hello friends",
            language="hi",
            translate_from_en=True,
            pen_id="ink",
            humanize=0,
        )
    ]
    layered = render_letter_layers(layers, seed=3)
    assert layered.meta.get("translate_pending") is True


def test_draft_api_accepts_layers_and_margins():
    r = client.post(
        "/api/letters/draft",
        json={
            "letter_type": "personal",
            "use_llm": False,
            "optimize": False,
            "highlight": False,
            "margins": {"left": 16, "top": 20, "right": 14, "bottom": 18},
            "layers": [
                {
                    "id": "layer-0",
                    "name": "Ink",
                    "body": "HELLO",
                    "font_name": "simplex",
                    "size_mm": 5,
                    "pen_id": "ink",
                    "language": "hi",
                    "translate_from_en": True,
                    "offset_x_mm": 0,
                    "offset_y_mm": 0,
                    "kind": "ink",
                }
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["settings"]["margins"]["top"] == 20
    assert data["settings"]["translate_pending"] is True
    assert "not processed" in (data["settings"]["translate_note"] or "")
    assert data["layers"]["passes"][0]["board_id"] == "BD-INK-01"
    assert data["emulator"]["segments"]


def test_layout_uses_named_font():
    polys, spans, meta = layout_text("Aa", x=0, y=0, font_name="scripts", humanize=0, size_mm=4)
    assert polys
    assert meta["font"] == "scripts"
