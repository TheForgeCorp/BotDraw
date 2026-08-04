"""Portrait ingest intermediate representation."""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, Field


class RegionPoly(BaseModel):
    """Closed region from tracer (pixel or mm space noted in meta)."""

    id: str
    points_mm: list[tuple[float, float]]
    mean_rgb: tuple[float, float, float]
    area: float = 0.0
    pen_id: str | None = None


class ColorCluster(BaseModel):
    id: str
    mean_rgb: tuple[float, float, float]
    area: float = 0.0
    default_pen_id: str | None = None


class CropRect(BaseModel):
    """Normalized crop in 0..1 image space (x,y = top-left)."""

    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0
    source: str = "full"  # full | auto | manual


class PortraitVector(BaseModel):
    """Shared ingest output for style restylers."""

    model_config = {"arbitrary_types_allowed": True}

    width_px: int
    height_px: int
    page_w_mm: float
    page_h_mm: float
    rgb: Any  # np.ndarray float32 HxWx3
    lum: Any  # np.ndarray float32 HxW
    ink_target: Any  # np.ndarray float32 HxW darkness 0..1
    edge_map: Any  # np.ndarray float32 HxW
    edge_polylines_mm: list[list[tuple[float, float]]] = Field(default_factory=list)
    regions: list[RegionPoly] = Field(default_factory=list)
    clusters: list[ColorCluster] = Field(default_factory=list)
    pen_map: dict[str, str] = Field(default_factory=dict)
    crop: CropRect = Field(default_factory=CropRect)
    image_mode: str = "photo"
    quality: str = "booth-balanced"
    ingest_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    def arrays(self) -> dict[str, np.ndarray]:
        return {
            "rgb": np.asarray(self.rgb, dtype=np.float32),
            "lum": np.asarray(self.lum, dtype=np.float32),
            "ink_target": np.asarray(self.ink_target, dtype=np.float32),
            "edge_map": np.asarray(self.edge_map, dtype=np.float32),
        }
