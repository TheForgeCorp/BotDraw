"""Style engine registry and base protocol."""

from __future__ import annotations

from typing import Callable, Protocol

from botdraw.core.models import LayeredSVG, PAPER_MM, PaperSize, PaletteSet, StyleParams


class StyleEngine(Protocol):
    id: str
    name: str
    category: str
    description: str

    def render(
        self,
        *,
        palette: PaletteSet,
        params: StyleParams,
        paper: PaperSize = PaperSize.A4,
        image_path: str | None = None,
        image_array=None,
    ) -> LayeredSVG: ...


_REGISTRY: dict[str, StyleEngine] = {}


def register(engine: StyleEngine) -> StyleEngine:
    _REGISTRY[engine.id] = engine
    return engine


def get_style(style_id: str) -> StyleEngine:
    if style_id not in _REGISTRY:
        raise KeyError(f"Unknown style: {style_id}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[style_id]


def list_styles(category: str | None = None) -> list[dict]:
    items = []
    for eng in _REGISTRY.values():
        if category and eng.category != category:
            continue
        items.append(
            {
                "id": eng.id,
                "name": eng.name,
                "category": eng.category,
                "description": eng.description,
            }
        )
    return sorted(items, key=lambda x: (x["category"], x["name"]))


def page_size(paper: PaperSize) -> tuple[float, float]:
    return PAPER_MM[paper]


def ensure_styles_loaded() -> None:
    # Import modules for side-effect registration
    from botdraw.styles import (  # noqa: F401
        artistic,
        fractals,
        obscure,
        patterns,
        portrait,
        spirograph,
        technical,
    )
