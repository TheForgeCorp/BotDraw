"""Sensor / telemetry → art (R&D Lab)."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.models import Orientation, PaperSize
from botdraw.data import MODES, data_to_layered, list_demos, load_demo, parse_bytes, parse_csv_text, parse_json_obj
from botdraw.data.map import (
    default_mode,
    is_geographic_lonlat,
    prepare_path_xy,
    web_mercator_project,
)


client = TestClient(app)


def test_list_demos():
    demos = list_demos()
    assert {d["id"] for d in demos} == {"temperature", "gps_walk", "gforce"}
    for d in demos:
        assert d["default_mode"] in MODES


@pytest.mark.parametrize("demo_id", ["temperature", "gps_walk", "gforce"])
def test_demo_loads(demo_id):
    rec = load_demo(demo_id)
    assert rec.kind in ("series", "path", "vectors")
    layered = data_to_layered(rec, mode=default_mode(rec.kind), seed=1)
    assert layered.width_mm > 0
    assert layered.meta["style"] == "sensor"
    assert layered.meta["kind"] == rec.kind
    assert sum(len(p.polylines) for p in layered.passes) >= 1


@pytest.mark.parametrize("mode", list(MODES))
def test_temperature_all_modes(mode):
    rec = load_demo("temperature")
    layered = data_to_layered(rec, mode=mode, folds=8, density=0.8)
    assert layered.meta["mode"] == mode
    assert layered.meta["strokes"] >= 1


def test_parse_series_json():
    rec = parse_json_obj({"kind": "series", "label": "temps", "unit": "C", "values": [1, 2, 3, 4, 5]})
    assert rec.kind == "series"
    assert len(rec.values) == 5


def test_parse_path_csv():
    text = "lon,lat\n-122.4,37.7\n-122.41,37.71\n-122.42,37.72\n"
    rec = parse_csv_text(text, label="walk")
    assert rec.kind == "path"
    assert len(rec.points) == 3


def test_parse_gforce_csv():
    text = "ax,ay,az\n0,0,1\n0.1,0,1.0\n0.2,-0.1,0.9\n"
    rec = parse_csv_text(text)
    assert rec.kind == "vectors"
    assert rec.samples.shape == (3, 3)


def test_parse_bytes_json_array():
    raw = json.dumps([10.0, 11.5, 9.0, 12.0]).encode()
    rec = parse_bytes(raw, filename="series.json")
    assert rec.kind == "series"
    layered = data_to_layered(rec, mode="mirror")
    assert layered.meta["mode"] == "mirror"


def test_mirror_is_bilateral():
    vals = np.sin(np.linspace(0, 4 * np.pi, 80))
    rec = parse_json_obj({"kind": "series", "values": vals.tolist()})
    layered = data_to_layered(rec, mode="mirror", paper=PaperSize.A4, orientation=Orientation.PORTRAIT)
    # two side strokes + optional spine
    assert layered.meta["strokes"] >= 2


def test_api_demos_list():
    r = client.get("/api/rdlab/sensor/demos")
    assert r.status_code == 200
    body = r.json()
    assert len(body["demos"]) == 3
    assert "ribbon" in body["modes"]


def test_api_sensor_demo_render():
    r = client.post(
        "/api/rdlab/sensor/demo",
        data={"demo_id": "gps_walk", "mode": "path", "seed": "3", "palette_id": "default-6"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["app"] == "rdlab"
    assert body["job"]["style_id"] == "sensor-path"
    assert body["layers"]["meta"]["kind"] == "path"
    assert body["emulator"]["settings"]["sensor"]["demo_id"] == "gps_walk"


def test_api_sensor_upload_csv():
    csv = b"value\n1\n2\n3\n4\n5\n6\n"
    r = client.post(
        "/api/rdlab/sensor/upload",
        data={"mode": "radial", "seed": "1"},
        files={"file": ("temps.csv", csv, "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["layers"]["meta"]["mode"] == "radial"


def test_api_bad_mode():
    r = client.post(
        "/api/rdlab/sensor/demo",
        data={"demo_id": "temperature", "mode": "not-a-mode"},
    )
    assert r.status_code == 400


def test_web_mercator_matches_gpx2svg_formula():
    """San Francisco lon/lat → EPSG:3857 metres (gpx2svg formula)."""
    lon, lat = -122.4194, 37.7749
    pts = web_mercator_project(np.array([[lon, lat]], dtype=np.float64))
    r = 6_378_137.0
    expected_x = math.radians(lon) * r
    expected_y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * r
    assert abs(pts[0, 0] - expected_x) < 1e-6
    assert abs(pts[0, 1] - expected_y) < 1e-6


def test_geographic_heuristic_and_prepare():
    gps = np.array([[-122.4, 37.7], [-122.41, 37.71], [-122.42, 37.72]])
    assert is_geographic_lonlat(gps, unit="deg", kind="path")
    assert is_geographic_lonlat(gps, kind="path")
    art = np.array([[0.0, 0.0], [0.2, 0.1], [0.5, 0.4]])
    assert not is_geographic_lonlat(art, kind="path")
    assert not is_geographic_lonlat(gps, kind="vectors")

    from botdraw.data.map import SensorRecord

    rec = SensorRecord(kind="path", label="walk", unit="deg", points=gps)
    xy = prepare_path_xy(rec)
    assert xy.shape == gps.shape
    # Projected metres are large absolute values
    assert abs(xy[0, 0]) > 1_000_000


def test_gps_path_uses_mercator_crs():
    rec = load_demo("gps_walk")
    layered = data_to_layered(rec, mode="path")
    assert layered.meta["crs"] == "web_mercator"
    # Aspect should not collapse: bounding box of strokes spans both axes
    pts = layered.passes[0].polylines[0].points
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert max(xs) - min(xs) > 10
    assert max(ys) - min(ys) > 10


def test_mercator_corrects_lon_lat_aspect_at_mid_latitudes():
    """1° lon vs 1° lat at 60°N must not keep equal span after projection."""
    # Square in degree space at high latitude is a wide rectangle in metres
    square_deg = np.array(
        [
            [10.0, 60.0],
            [11.0, 60.0],
            [11.0, 61.0],
            [10.0, 61.0],
            [10.0, 60.0],
        ]
    )
    merc = web_mercator_project(square_deg)
    span_x = float(merc[:, 0].max() - merc[:, 0].min())
    span_y = float(merc[:, 1].max() - merc[:, 1].min())
    # At 60°N, 1° lon ≈ half of 1° lat in metres (cos60=0.5); Mercator
    # stretches Y further, so span_x < span_y clearly.
    assert span_x < span_y * 0.85


def test_cartesian_path_skips_mercator():
    pts = np.array([[0.0, 0.0], [100.0, 50.0], [200.0, 0.0]])  # outside lat range
    rec = parse_json_obj({"kind": "path", "unit": "mm", "points": pts.tolist()})
    layered = data_to_layered(rec, mode="path")
    assert layered.meta["crs"] == "cartesian"
