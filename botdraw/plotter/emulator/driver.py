"""Software plotter emulator — replays motion plans with timing."""

from __future__ import annotations

import time
from typing import Any

from botdraw.core.motion_plan import MotionPlan, SegmentKind
from botdraw.plotter import PlotterDriver, ProgressCallback


class EmulatorDriver(PlotterDriver):
    name = "emulator"

    def __init__(self) -> None:
        self._connected = False
        self.last_frame: dict[str, Any] | None = None

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def plot(
        self,
        plan: MotionPlan,
        *,
        on_progress: ProgressCallback | None = None,
        speed_multiplier: float = 1.0,
        realtime: bool = False,
    ) -> dict:
        if not self._connected:
            self.connect()
        ink_segments = []
        t = 0.0
        total = max(plan.stats.estimated_time_s, 1e-6)
        for i, seg in enumerate(plan.segments):
            dur = seg.duration_s / max(speed_multiplier, 1e-6)
            if realtime and dur > 0:
                time.sleep(min(dur, 0.05))
            frame = {
                "index": i,
                "kind": seg.kind.value,
                "x0": seg.x0,
                "y0": seg.y0,
                "x1": seg.x1,
                "y1": seg.y1,
                "pen_id": seg.pen_id,
                "pass_id": seg.pass_id,
                "color_hex": seg.color_hex,
                "width_mm": seg.width_mm,
                "opacity": seg.opacity,
                "base_theta_rad": seg.base_theta_rad,
                "t": t,
            }
            if seg.kind == SegmentKind.PEN_DOWN:
                ink_segments.append(frame)
            self.last_frame = frame
            t += dur
            if on_progress:
                on_progress(min(1.0, t / total), seg.kind.value)
        return {
            "driver": self.name,
            "ink_segments": ink_segments,
            "segment_count": len(plan.segments),
            "stats": plan.stats.model_dump(),
            "elapsed_s": t,
        }


def plan_to_emulator_payload(plan: MotionPlan) -> dict[str, Any]:
    """JSON payload for the frontend canvas player."""
    return {
        "schema_version": plan.schema_version,
        "width_mm": plan.width_mm,
        "height_mm": plan.height_mm,
        "stats": plan.stats.model_dump(),
        "palette": [p.model_dump() for p in plan.palette_snapshot],
        "segments": [s.model_dump(mode="json") for s in plan.segments],
    }
