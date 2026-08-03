"""Typed motion plan contract shared by emulator and plotter drivers."""

from __future__ import annotations

import json
import math
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from botdraw.core.models import LayeredSVG, PaletteSet

SCHEMA_VERSION = "1.0.0"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "motion_plan.schema.json"

DEFAULT_PEN_UP_MM_S = 100.0
DEFAULT_PEN_DOWN_MM_S = 25.0
PEN_CHANGE_DWELL_S = 2.0


class SegmentKind(str, Enum):
    PEN_UP = "pen_up"
    PEN_DOWN = "pen_down"
    PEN_CHANGE = "pen_change"
    DWELL = "dwell"


class MotionSegment(BaseModel):
    kind: SegmentKind
    x0: float
    y0: float
    x1: float
    y1: float
    duration_s: float
    pen_id: str | None = None
    pass_id: str | None = None
    base_theta_rad: float | None = None
    opacity: float | None = None
    width_mm: float | None = None
    color_hex: str | None = None


class MotionStats(BaseModel):
    path_length_mm: float
    pen_up_travel_mm: float
    pen_down_travel_mm: float
    estimated_time_s: float
    stroke_count: int
    pass_count: int
    pen_ids: list[str]


class PenSnapshot(BaseModel):
    id: str
    name: str
    color_hex: str
    width_mm: float
    opacity: float
    nib_type: str


class MotionPlan(BaseModel):
    schema_version: str = SCHEMA_VERSION
    width_mm: float
    height_mm: float
    pen_up_speed_mm_s: float = DEFAULT_PEN_UP_MM_S
    pen_down_speed_mm_s: float = DEFAULT_PEN_DOWN_MM_S
    segments: list[MotionSegment] = Field(default_factory=list)
    stats: MotionStats
    palette_snapshot: list[PenSnapshot] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> MotionPlan:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def compile_motion_plan(
    layered: LayeredSVG,
    palette: PaletteSet,
    *,
    pen_up_speed_mm_s: float = DEFAULT_PEN_UP_MM_S,
    pen_down_speed_mm_s: float = DEFAULT_PEN_DOWN_MM_S,
    include_base_theta: bool = False,
) -> MotionPlan:
    """Compile layered SVG geometry into a timed motion plan."""
    segments: list[MotionSegment] = []
    cursor = (0.0, 0.0)
    pen_up = 0.0
    pen_down = 0.0
    stroke_count = 0
    pen_ids: list[str] = []
    current_pen: str | None = None
    total_time = 0.0

    for pass_layer in layered.passes:
        pen = palette.pen_by_id(pass_layer.pen_id)
        opacity = pass_layer.opacity_override if pass_layer.opacity_override is not None else pen.profile.opacity
        if current_pen != pen.id:
            if current_pen is not None:
                dwell = MotionSegment(
                    kind=SegmentKind.PEN_CHANGE,
                    x0=cursor[0],
                    y0=cursor[1],
                    x1=cursor[0],
                    y1=cursor[1],
                    duration_s=PEN_CHANGE_DWELL_S,
                    pen_id=pen.id,
                    pass_id=pass_layer.id,
                    opacity=opacity,
                    width_mm=pen.profile.width_mm,
                    color_hex=pen.color_hex,
                )
                segments.append(dwell)
                total_time += PEN_CHANGE_DWELL_S
            current_pen = pen.id
            if pen.id not in pen_ids:
                pen_ids.append(pen.id)

        for poly in pass_layer.polylines:
            if len(poly.points) < 2:
                continue
            start = poly.points[0]
            travel = _dist(cursor, start)
            dur_up = travel / pen_up_speed_mm_s if pen_up_speed_mm_s > 0 else 0.0
            segments.append(
                MotionSegment(
                    kind=SegmentKind.PEN_UP,
                    x0=cursor[0],
                    y0=cursor[1],
                    x1=start[0],
                    y1=start[1],
                    duration_s=dur_up,
                    pen_id=pen.id,
                    pass_id=pass_layer.id,
                    opacity=opacity,
                    width_mm=pen.profile.width_mm,
                    color_hex=pen.color_hex,
                    base_theta_rad=0.0 if include_base_theta else None,
                )
            )
            pen_up += travel
            total_time += dur_up
            cursor = start
            stroke_count += 1

            pts = list(poly.points)
            if poly.closed and pts[0] != pts[-1]:
                pts.append(pts[0])
            for i in range(1, len(pts)):
                a, b = pts[i - 1], pts[i]
                d = _dist(a, b)
                dur = d / pen_down_speed_mm_s if pen_down_speed_mm_s > 0 else 0.0
                theta = None
                if include_base_theta:
                    # Spiral-friendly: angle from page center
                    cx, cy = layered.width_mm / 2, layered.height_mm / 2
                    theta = math.atan2(b[1] - cy, b[0] - cx)
                segments.append(
                    MotionSegment(
                        kind=SegmentKind.PEN_DOWN,
                        x0=a[0],
                        y0=a[1],
                        x1=b[0],
                        y1=b[1],
                        duration_s=dur,
                        pen_id=pen.id,
                        pass_id=pass_layer.id,
                        opacity=opacity,
                        width_mm=pen.profile.width_mm,
                        color_hex=pen.color_hex,
                        base_theta_rad=theta,
                    )
                )
                pen_down += d
                total_time += dur
                cursor = b

    stats = MotionStats(
        path_length_mm=pen_up + pen_down,
        pen_up_travel_mm=pen_up,
        pen_down_travel_mm=pen_down,
        estimated_time_s=total_time,
        stroke_count=stroke_count,
        pass_count=len(layered.passes),
        pen_ids=pen_ids,
    )
    snapshot = [
        PenSnapshot(
            id=p.id,
            name=p.name,
            color_hex=p.color_hex,
            width_mm=p.profile.width_mm,
            opacity=p.profile.opacity,
            nib_type=p.profile.nib_type.value,
        )
        for p in palette.pens
    ]
    return MotionPlan(
        width_mm=layered.width_mm,
        height_mm=layered.height_mm,
        pen_up_speed_mm_s=pen_up_speed_mm_s,
        pen_down_speed_mm_s=pen_down_speed_mm_s,
        segments=segments,
        stats=stats,
        palette_snapshot=snapshot,
    )
