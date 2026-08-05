"""Stroke fonts for LettersBot."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FONT_DIR = Path(__file__).parent

# Display order for Dev Panel picker
FONT_CATALOG = (
    ("simplex", "Hershey Sans (stroke)"),
    ("timesr", "Hershey Serif (stroke)"),
    ("scripts", "Hershey Script (stroke)"),
)


def list_fonts() -> list[dict[str, str]]:
    out = []
    for font_id, fallback_label in FONT_CATALOG:
        path = FONT_DIR / f"{font_id}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "id": font_id,
                "label": data.get("label") or fallback_label,
                "name": data.get("name", font_id),
            }
        )
    return out


@lru_cache(maxsize=8)
def load_font(name: str = "simplex") -> dict[str, Any]:
    path = FONT_DIR / f"{name}.json"
    if not path.exists():
        path = FONT_DIR / "simplex.json"
    return json.loads(path.read_text(encoding="utf-8"))


def glyph_for(ch: str, font: dict[str, Any] | None = None) -> dict[str, Any] | None:
    font = font or load_font()
    glyphs = font["glyphs"]
    if ch in glyphs:
        return glyphs[ch]
    return None
