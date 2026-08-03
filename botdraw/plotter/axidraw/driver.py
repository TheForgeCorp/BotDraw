"""AxiDraw driver stub + future hardware integration hooks."""

from __future__ import annotations

import logging
from typing import Any

from botdraw.core.motion_plan import MotionPlan
from botdraw.plotter import PlotterDriver, ProgressCallback

log = logging.getLogger(__name__)


class AxiDrawDriverStub(PlotterDriver):
    """Interface-only stub — logs intended plot actions without hardware."""

    name = "axidraw-stub"

    def __init__(self) -> None:
        self._connected = False
        self.would_plot_log: list[dict[str, Any]] = []

    def connect(self) -> None:
        self._connected = True
        log.info("AxiDraw stub connected (no hardware)")

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
    ) -> dict:
        if not self._connected:
            self.connect()
        entry = {
            "action": "would_plot",
            "segments": len(plan.segments),
            "eta_s": plan.stats.estimated_time_s / max(speed_multiplier, 1e-6),
            "pens": plan.stats.pen_ids,
        }
        self.would_plot_log.append(entry)
        log.info("AxiDraw stub would plot: %s", entry)
        if on_progress:
            on_progress(1.0, "stub-complete")
        return {"driver": self.name, **entry, "ok": True}


class AxiDrawDriver(PlotterDriver):
    """
    Real hardware driver shell.

    Attempts pyaxidraw when installed; otherwise raises with setup guidance.
    ETA calibration hooks compare wall-clock to motion plan estimates.
    """

    name = "axidraw"

    def __init__(self) -> None:
        self._connected = False
        self._ad = None
        self.eta_calibration_factor: float = 1.0
        self.last_wall_clock_s: float | None = None

    def connect(self) -> None:
        try:
            from pyaxidraw import axidraw  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "pyaxidraw not available. Install AxiDraw API and connect hardware, "
                "or use EmulatorDriver / AxiDrawDriverStub."
            ) from exc
        self._ad = axidraw.AxiDraw()
        self._ad.interactive()
        if not self._ad.connect():
            raise RuntimeError("AxiDraw connect() failed — check USB and power")
        self._connected = True

    def disconnect(self) -> None:
        if self._ad is not None:
            try:
                self._ad.disconnect()
            except Exception:
                pass
        self._connected = False
        self._ad = None

    def is_connected(self) -> bool:
        return self._connected

    def calibrate_eta(self, estimated_s: float, wall_clock_s: float) -> float:
        if estimated_s <= 0:
            return self.eta_calibration_factor
        self.eta_calibration_factor = wall_clock_s / estimated_s
        return self.eta_calibration_factor

    def plot(
        self,
        plan: MotionPlan,
        *,
        on_progress: ProgressCallback | None = None,
        speed_multiplier: float = 1.0,
    ) -> dict:
        import time

        if not self._connected or self._ad is None:
            raise RuntimeError("AxiDraw not connected")
        t0 = time.time()
        # Interactive path following — simplified lineto/moveto mapping
        total = max(len(plan.segments), 1)
        for i, seg in enumerate(plan.segments):
            # AxiDraw interactive uses inches
            x1, y1 = seg.x1 / 25.4, seg.y1 / 25.4
            if seg.kind.value == "pen_up":
                self._ad.moveto(x1, y1)
            elif seg.kind.value == "pen_down":
                self._ad.lineto(x1, y1)
            if on_progress:
                on_progress((i + 1) / total, seg.kind.value)
        wall = time.time() - t0
        self.last_wall_clock_s = wall
        factor = self.calibrate_eta(plan.stats.estimated_time_s, wall)
        return {
            "driver": self.name,
            "wall_clock_s": wall,
            "estimated_s": plan.stats.estimated_time_s,
            "eta_calibration_factor": factor,
            "ok": True,
        }
