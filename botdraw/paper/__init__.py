"""Paper Library presets (stocks with color + finish)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

PRESET_DIR = Path(__file__).parent / "presets"
USER_DIR = Path(__file__).resolve().parents[2] / "jobs" / "paper"


class PaperStock(BaseModel):
    id: str
    name: str
    color_hex: str = "#f7f1e8"
    finish: str = "matte"  # matte | smooth | toothy
    size_hint: str | None = "A4"
    notes: str = ""


DEFAULT_PAPER_ID = "natural-cream"


def _ensure_presets() -> None:
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    seeds = [
        PaperStock(id="bright-white", name="Bright White", color_hex="#ffffff", finish="smooth"),
        PaperStock(id="natural-cream", name="Natural Cream", color_hex="#f7f1e8", finish="matte", notes="Default emulator cream"),
        PaperStock(id="warm-ivory", name="Warm Ivory", color_hex="#f3e6d0", finish="matte"),
        PaperStock(id="soft-gray", name="Soft Gray", color_hex="#e6e6e4", finish="smooth"),
        PaperStock(id="kraft", name="Kraft", color_hex="#c4a574", finish="toothy"),
        PaperStock(id="black", name="Black", color_hex="#1a1a1a", finish="smooth"),
        PaperStock(id="blush", name="Blush", color_hex="#f2d6d0", finish="matte"),
        PaperStock(id="pale-blue", name="Pale Blue", color_hex="#d9e4ef", finish="smooth"),
    ]
    for s in seeds:
        path = PRESET_DIR / f"{s.id}.json"
        if not path.exists():
            path.write_text(s.model_dump_json(indent=2), encoding="utf-8")


def list_paper_ids() -> list[str]:
    _ensure_presets()
    ids = {p.stem for p in PRESET_DIR.glob("*.json")}
    if USER_DIR.exists():
        ids |= {p.stem for p in USER_DIR.glob("*.json")}
    return sorted(ids)


def load_paper(paper_id: str | None = None) -> PaperStock:
    _ensure_presets()
    pid = paper_id or DEFAULT_PAPER_ID
    for folder in (USER_DIR, PRESET_DIR):
        path = folder / f"{pid}.json"
        if path.exists():
            return PaperStock.model_validate_json(path.read_text(encoding="utf-8"))
    return load_paper(DEFAULT_PAPER_ID)


def list_papers() -> list[dict]:
    return [load_paper(pid).model_dump() for pid in list_paper_ids()]


def resolve_paper_color(paper_id: str | None = None, paper_color_hex: str | None = None) -> tuple[str, str]:
    """Return (paper_id, color_hex)."""
    if paper_color_hex:
        return paper_id or "custom", paper_color_hex
    stock = load_paper(paper_id or DEFAULT_PAPER_ID)
    return stock.id, stock.color_hex
