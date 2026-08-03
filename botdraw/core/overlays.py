"""Ordered overlay / rewrite pass composition."""

from __future__ import annotations

from uuid import uuid4

from botdraw.core.models import LayeredSVG, PassLayer, Polyline
from botdraw.core.svg import make_pass


class OverlayPassComposer:
    """Compose intentional multi-pass artworks (ink → highlight → ornament)."""

    def compose(
        self,
        width_mm: float,
        height_mm: float,
        passes: list[PassLayer],
        *,
        seed: int | None = None,
        meta: dict | None = None,
    ) -> LayeredSVG:
        return LayeredSVG(
            width_mm=width_mm,
            height_mm=height_mm,
            passes=list(passes),
            seed=seed,
            meta=meta or {},
        )

    def append_pass(self, layered: LayeredSVG, pass_layer: PassLayer) -> LayeredSVG:
        layered.passes.append(pass_layer)
        return layered

    def highlight_spans(
        self,
        layered: LayeredSVG,
        spans: list[dict],
        *,
        pen_id: str,
        pad_mm: float = 0.8,
        opacity: float = 0.45,
        stroke_width_mm: float = 2.4,
    ) -> LayeredSVG:
        """
        Add highlighter strokes over glyph/word bounding boxes.

        Each span dict: {x, y, w, h} in mm paper coordinates.
        Uses a few parallel strokes so the mark reads as a highlighter
        band without covering the whole letter body.
        """
        polys: list[Polyline] = []
        # Cap band height so highlights stay local to the word.
        band = min(max(stroke_width_mm, 1.2), max(1.2, spans[0]["h"] * 0.55) if spans else stroke_width_mm)
        offsets = (-band * 0.28, 0.0, band * 0.28) if band >= 1.8 else (0.0,)
        for span in spans:
            x, y, w, h = span["x"], span["y"], span["w"], span["h"]
            y_mid = y + h * 0.55
            x0, x1 = x - pad_mm, x + w + pad_mm
            for dy in offsets:
                polys.append(
                    Polyline(
                        points=[(x0, y_mid + dy), (x1, y_mid + dy)],
                        pen_id=pen_id,
                    )
                )
        highlight = make_pass(
            f"highlight-{uuid4().hex[:8]}",
            "Highlight rewrite",
            pen_id,
            polys,
            kind="highlight",
            opacity_override=opacity,
        )
        return self.append_pass(layered, highlight)

    def stack(self, base: LayeredSVG, *overlays: LayeredSVG) -> LayeredSVG:
        out = base.model_copy(deep=True)
        for overlay in overlays:
            out.passes.extend(overlay.passes)
        return out
