"""Stroke fonts for LettersBot."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FONT_DIR = Path(__file__).parent


@lru_cache(maxsize=4)
def load_font(name: str = "simplex") -> dict[str, Any]:
    path = FONT_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def glyph_for(ch: str, font: dict[str, Any] | None = None) -> dict[str, Any] | None:
    font = font or load_font()
    glyphs = font["glyphs"]
    if ch in glyphs:
        return glyphs[ch]
    return None
