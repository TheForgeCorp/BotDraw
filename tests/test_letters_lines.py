"""Line layers, dash expansion, snap, leading variation, line angle."""

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.letters import (
    LetterLayerSpec,
    LineGeom,
    SnapSpec,
    layout_text,
    render_letter_layers,
)


client = TestClient(app)


def _bounds_y(layered, pass_idx=0):
    ys = [y for pl in layered.passes[pass_idx].polylines for _, y in pl.points]
    return min(ys), max(ys)


def test_line_solid_endpoints():
    layers = [
        LetterLayerSpec(
            id="ln",
            name="UL",
            draw_mode="line",
            kind="underline",
            pen_id="ink",
            placement="freehand",
            line=LineGeom(x0_mm=10, y0_mm=30, x1_mm=80, y1_mm=32, style="solid"),
        )
    ]
    layered = render_letter_layers(layers, seed=1)
    assert len(layered.passes) == 1
    pts = layered.passes[0].polylines[0].points
    assert abs(pts[0][0] - 10) < 1e-6
    assert abs(pts[0][1] - 30) < 1e-6
    assert abs(pts[-1][0] - 80) < 1e-6
    assert abs(pts[-1][1] - 32) < 1e-6


def test_line_dashed_segments():
    layers = [
        LetterLayerSpec(
            id="ln",
            draw_mode="line",
            kind="underline",
            pen_id="ink",
            line=LineGeom(
                x0_mm=0, y0_mm=0, x1_mm=20, y1_mm=0, style="dashed", dash_mm=2, gap_mm=1
            ),
        )
    ]
    layered = render_letter_layers(layers, seed=1)
    polys = layered.passes[0].polylines
    assert len(polys) >= 4
    # First dash ~2mm
    d0 = abs(polys[0].points[1][0] - polys[0].points[0][0])
    assert abs(d0 - 2.0) < 0.05


def test_snap_underline_uses_span():
    layers = [
        LetterLayerSpec(id="t", body="HELLO", humanize=0, leading_variation=0, pen_id="ink"),
        LetterLayerSpec(
            id="ln",
            draw_mode="line",
            kind="underline",
            pen_id="rose",
            placement="snap",
            snap=SnapSpec(target_layer_id="t", span_index=0, role="underline"),
            line=LineGeom(x0_mm=0, y0_mm=0, x1_mm=1, y1_mm=1),
        ),
    ]
    layered = render_letter_layers(layers, seed=2)
    spans = layered.meta["layer_spans"]["t"]
    assert spans
    pts = layered.passes[1].polylines[0].points
    assert pts[1][0] > pts[0][0]
    # Underline should sit near/below the span
    assert pts[0][1] >= spans[0]["y"]


def test_leading_variation_changes_spacing():
    body = "AAAA\nBBBB\nCCCC"
    a, sa, _ = layout_text(body, x=10, y=10, humanize=0, leading_variation=0, seed=9)
    b, sb, _ = layout_text(body, x=10, y=10, humanize=0, leading_variation=1.0, seed=9)
    ya = sorted({round(s["y"], 3) for s in sa})
    yb = sorted({round(s["y"], 3) for s in sb})
    assert len(ya) >= 2 and len(yb) >= 2
    gaps_a = [ya[i + 1] - ya[i] for i in range(len(ya) - 1)]
    gaps_b = [yb[i + 1] - yb[i] for i in range(len(yb) - 1)]
    assert gaps_a != gaps_b


def test_line_angle_rotates_points():
    body = "HELLO"
    p0, s0, m0 = layout_text(body, x=20, y=30, humanize=0, line_angle_deg=0, seed=1)
    p1, s1, m1 = layout_text(body, x=20, y=30, humanize=0, line_angle_deg=0.5, seed=1)
    assert m1["line_angle_deg"] == 0.5
    assert p0 and p1
    assert p0[0].points[0] != p1[0].points[0]
    assert s1


def test_draft_api_line_and_spans():
    r = client.post(
        "/api/letters/draft",
        json={
            "use_llm": False,
            "optimize": False,
            "highlight": False,
            "layers": [
                {
                    "id": "layer-0",
                    "name": "Ink",
                    "draw_mode": "text",
                    "body": "HELLO forever",
                    "font_name": "simplex",
                    "size_mm": 5,
                    "pen_id": "ink",
                    "humanize": 0,
                    "leading_variation": 0.1,
                    "line_angle_deg": 0.25,
                },
                {
                    "id": "layer-line",
                    "name": "UL",
                    "draw_mode": "line",
                    "kind": "underline",
                    "pen_id": "rose",
                    "placement": "snap",
                    "snap": {
                        "target_layer_id": "layer-0",
                        "span_index": 0,
                        "role": "underline",
                    },
                    "line": {
                        "x0_mm": 0,
                        "y0_mm": 0,
                        "x1_mm": 10,
                        "y1_mm": 0,
                        "style": "dashed",
                        "dash_mm": 1.5,
                        "gap_mm": 1.0,
                    },
                },
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "layer-0" in data["settings"]["layer_spans"]
    assert len(data["layers"]["passes"]) == 2
    assert data["emulator"]["segments"]
