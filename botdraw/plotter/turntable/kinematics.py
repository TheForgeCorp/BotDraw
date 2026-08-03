"""Rotating base / turntable kinematics helpers for R&D Lab."""

from __future__ import annotations

import math

from botdraw.core.models import LayeredSVG, Polyline
from botdraw.core.motion_plan import MotionPlan, MotionSegment, SegmentKind, compile_motion_plan
from botdraw.core.models import PaletteSet


def world_to_joint(
    x: float,
    y: float,
    *,
    cx: float,
    cy: float,
    theta: float,
) -> tuple[float, float]:
    """Transform world point into plotter frame given base rotation theta."""
    dx, dy = x - cx, y - cy
    c, s = math.cos(-theta), math.sin(-theta)
    return cx + dx * c - dy * s, cy + dx * s + dy * c


def annotate_plan_with_rotation(
    plan: MotionPlan,
    *,
    rpm: float = 2.0,
) -> MotionPlan:
    """Fill base_theta_rad along the timeline for emulator turntable playback."""
    omega = rpm * 2 * math.pi / 60.0
    t = 0.0
    segs: list[MotionSegment] = []
    for seg in plan.segments:
        segs.append(
            seg.model_copy(update={"base_theta_rad": omega * t})
        )
        t += seg.duration_s
    return plan.model_copy(update={"segments": segs})


def spiral_on_turntable(
    layered: LayeredSVG,
    palette: PaletteSet,
    *,
    rpm: float = 3.0,
) -> MotionPlan:
    plan = compile_motion_plan(layered, palette, include_base_theta=True)
    return annotate_plan_with_rotation(plan, rpm=rpm)


def rotate_polylines(polys: list[Polyline], angle_rad: float, cx: float, cy: float) -> list[Polyline]:
    out: list[Polyline] = []
    for poly in polys:
        pts = [world_to_joint(x, y, cx=cx, cy=cy, theta=angle_rad) for x, y in poly.points]
        out.append(Polyline(points=pts, pen_id=poly.pen_id, closed=poly.closed))
    return out
