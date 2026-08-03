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
    ) -> LayeredSVG:
        """
        Add highlighter strokes over glyph/word bounding boxes.

        Each span dict: {x, y, w, h} in mm paper coordinates.
        """
        polys: list[Polyline] = []
        for span in spans:
            x, y, w, h = span["x"], span["y"], span["w"], span["h"]
            y_mid = y + h / 2
            polys.append(
                Polyline(
                    points=[(x - pad_mm, y_mid), (x + w + pad_mm, y_mid)],
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
