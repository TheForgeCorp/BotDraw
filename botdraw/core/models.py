"""Shared domain models: pens, palettes, passes, jobs, SVG layers."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class NibType(str, Enum):
    FINELINER = "fineliner"
    MARKER = "marker"
    BRUSH = "brush"
    CALLIGRAPHY = "calligraphy"
    HIGHLIGHTER = "highlighter"


class QualityPreset(str, Enum):
    BOOTH_FAST = "booth-fast"
    BOOTH_BALANCED = "booth-balanced"
    STUDIO_HQ = "studio-hq"


class PaperSize(str, Enum):
    A4 = "A4"
    LETTER = "Letter"
    A3 = "A3"
    A5 = "A5"
    CARD = "Card"


class Orientation(str, Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


PAPER_MM: dict[PaperSize, tuple[float, float]] = {
    PaperSize.A4: (210.0, 297.0),
    PaperSize.LETTER: (215.9, 279.4),
    PaperSize.A3: (297.0, 420.0),
    PaperSize.A5: (148.0, 210.0),
    PaperSize.CARD: (127.0, 178.0),
}


def paper_dims(
    paper: PaperSize, orientation: Orientation = Orientation.PORTRAIT
) -> tuple[float, float]:
    """Paper (width, height) in mm for the given orientation."""
    w, h = PAPER_MM[paper]
    if orientation == Orientation.LANDSCAPE:
        return h, w
    return w, h


class LineProfile(BaseModel):
    width_mm: float = 0.5
    min_width_mm: float = 0.3
    max_width_mm: float = 0.7
    nib_type: NibType = NibType.FINELINER
    calligraphy_angle_deg: float | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    bleed_hint: float = 0.0


class Pen(BaseModel):
    id: str
    name: str
    color_hex: str = "#000000"
    # Stable sample-board code for hardware / calibration mapping (e.g. BD-INK-01).
    board_id: str | None = None
    lab: tuple[float, float, float] | None = None
    profile: LineProfile = Field(default_factory=LineProfile)

    def resolved_board_id(self) -> str:
        return self.board_id or f"BD-{self.id.upper()}"


class PaletteSet(BaseModel):
    id: str
    name: str
    pens: list[Pen]
    paper_notes: str = ""
    calibration_samples: list[str] = Field(default_factory=list)

    def pen_by_id(self, pen_id: str) -> Pen:
        for pen in self.pens:
            if pen.id == pen_id:
                return pen
        raise KeyError(f"Pen not found: {pen_id}")


class Polyline(BaseModel):
    """A single continuous stroke in mm coordinates (paper space)."""

    points: list[tuple[float, float]]
    pen_id: str
    closed: bool = False


class PassLayer(BaseModel):
    """One ordered drawing pass bound to a palette pen."""

    id: str
    name: str
    pen_id: str
    polylines: list[Polyline] = Field(default_factory=list)
    opacity_override: float | None = None
    kind: str = "ink"  # ink | highlight | ornament | fill


class LayeredSVG(BaseModel):
    """Canonical multi-pass artwork before optimize/motion."""

    width_mm: float
    height_mm: float
    passes: list[PassLayer] = Field(default_factory=list)
    seed: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class JobStatus(str, Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"
    PLOTTING = "plotting"
    DONE = "done"


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    app: str
    style_id: str
    status: JobStatus = JobStatus.PENDING
    seed: int | None = None
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED
    palette_id: str = "default-6"
    paper: PaperSize = PaperSize.A4
    orientation: Orientation = Orientation.PORTRAIT
    params: dict[str, Any] = Field(default_factory=dict)
    svg_path: str | None = None
    motion_path: str | None = None
    preview_path: str | None = None
    error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


class StyleParams(BaseModel):
    seed: int = 42
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED
    density: float = 1.0
    scale: float = 1.0
    pen_count: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


QUALITY_LIMITS: dict[QualityPreset, dict[str, float | int]] = {
    QualityPreset.BOOTH_FAST: {
        "max_dots": 1500,
        "max_paths": 800,
        "image_max": 400,
        "lloyd_iters": 8,
        "spiral_turns": 40,
    },
    QualityPreset.BOOTH_BALANCED: {
        "max_dots": 4000,
        "max_paths": 2500,
        "image_max": 640,
        "lloyd_iters": 16,
        "spiral_turns": 80,
    },
    QualityPreset.STUDIO_HQ: {
        "max_dots": 12000,
        "max_paths": 8000,
        "image_max": 1024,
        "lloyd_iters": 30,
        "spiral_turns": 160,
    },
}
