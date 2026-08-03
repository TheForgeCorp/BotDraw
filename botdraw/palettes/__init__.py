"""Palette set storage and simple calibration trainer."""

from __future__ import annotations

import json
from pathlib import Path

from botdraw.core.models import LineProfile, NibType, PaletteSet, Pen

PRESET_DIR = Path(__file__).parent / "presets"
USER_DIR = Path(__file__).resolve().parents[2] / "jobs" / "palettes"


def _ensure_user_dir() -> Path:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DIR


def list_palette_ids() -> list[str]:
    ids = {p.stem for p in PRESET_DIR.glob("*.json")}
    if USER_DIR.exists():
        ids |= {p.stem for p in USER_DIR.glob("*.json")}
    return sorted(ids)


def load_palette(palette_id: str) -> PaletteSet:
    for folder in (USER_DIR, PRESET_DIR):
        path = folder / f"{palette_id}.json"
        if path.exists():
            return PaletteSet.model_validate_json(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Palette not found: {palette_id}")


def save_palette(palette: PaletteSet) -> Path:
    path = _ensure_user_dir() / f"{palette.id}.json"
    path.write_text(palette.model_dump_json(indent=2), encoding="utf-8")
    return path


def create_palette(
    palette_id: str,
    name: str,
    pens: list[dict],
    *,
    paper_notes: str = "",
) -> PaletteSet:
    pen_models: list[Pen] = []
    for p in pens:
        profile_data = p.get("profile", {})
        if "nib_type" in profile_data and isinstance(profile_data["nib_type"], str):
            profile_data = {**profile_data, "nib_type": NibType(profile_data["nib_type"])}
        pen_models.append(
            Pen(
                id=p["id"],
                name=p["name"],
                color_hex=p.get("color_hex", "#000000"),
                profile=LineProfile(**profile_data) if profile_data else LineProfile(),
            )
        )
    palette = PaletteSet(id=palette_id, name=name, pens=pen_models, paper_notes=paper_notes)
    save_palette(palette)
    return palette


def calibrate_pen(
    palette_id: str,
    pen_id: str,
    *,
    color_hex: str | None = None,
    width_mm: float | None = None,
    opacity: float | None = None,
    nib_type: str | None = None,
    sample_path: str | None = None,
) -> PaletteSet:
    """Update a pen's measured profile from manual calibration or photo path."""
    palette = load_palette(palette_id)
    pens = []
    for pen in palette.pens:
        if pen.id != pen_id:
            pens.append(pen)
            continue
        profile = pen.profile.model_copy()
        if width_mm is not None:
            profile.width_mm = width_mm
            profile.min_width_mm = width_mm * 0.8
            profile.max_width_mm = width_mm * 1.2
        if opacity is not None:
            profile.opacity = opacity
        if nib_type is not None:
            profile.nib_type = NibType(nib_type)
        pens.append(
            pen.model_copy(
                update={
                    "color_hex": color_hex or pen.color_hex,
                    "profile": profile,
                }
            )
        )
    samples = list(palette.calibration_samples)
    if sample_path:
        samples.append(sample_path)
    updated = palette.model_copy(update={"pens": pens, "calibration_samples": samples})
    save_palette(updated)
    return updated


def nearest_pen(palette: PaletteSet, r: int, g: int, b: int) -> Pen:
    """Quantize an RGB color onto the nearest palette pen (ignore highlighters by default)."""
    best = palette.pens[0]
    best_d = float("inf")
    for pen in palette.pens:
        if pen.profile.nib_type == NibType.HIGHLIGHTER:
            continue
        hex_color = pen.color_hex.lstrip("#")
        pr, pg, pb = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if d < best_d:
            best_d = d
            best = pen
    return best


def ink_pens(palette: PaletteSet) -> list[Pen]:
    return [p for p in palette.pens if p.profile.nib_type != NibType.HIGHLIGHTER]
