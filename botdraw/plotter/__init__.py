"""Plotter driver interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from botdraw.core.motion_plan import MotionPlan


ProgressCallback = Callable[[float, str], None]


class PlotterDriver(ABC):
    """Common interface for emulator and physical plotters."""

    name: str = "base"

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def plot(
        self,
        plan: MotionPlan,
        *,
        on_progress: ProgressCallback | None = None,
        speed_multiplier: float = 1.0,
    ) -> dict:
        ...

    def is_connected(self) -> bool:
        return False
