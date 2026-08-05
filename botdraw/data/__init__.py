"""Real-world sensor / telemetry data → pen-plotter art.

Parse CSV or JSON into typed records (series, path, vectors), then map them
into LayeredSVG with visual modes: ribbon, mirror, radial, spiral, path, mandala.
"""

from __future__ import annotations

from botdraw.data.demos import DEMO_IDS, list_demos, load_demo
from botdraw.data.map import (
    MODES,
    SensorRecord,
    data_to_layered,
    is_geographic_lonlat,
    prepare_path_xy,
    render_demo,
    render_file,
    web_mercator_project,
)
from botdraw.data.parse import parse_bytes, parse_csv_text, parse_json_obj

__all__ = [
    "DEMO_IDS",
    "MODES",
    "SensorRecord",
    "data_to_layered",
    "is_geographic_lonlat",
    "list_demos",
    "load_demo",
    "parse_bytes",
    "parse_csv_text",
    "parse_json_obj",
    "prepare_path_xy",
    "render_demo",
    "render_file",
    "web_mercator_project",
]
