"""Sensor / telemetry → art (R&D Lab)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.core.models import Orientation, PaperSize
from botdraw.data import MODES, data_to_layered, list_demos, load_demo, parse_bytes, parse_csv_text, parse_json_obj
from botdraw.data.map import default_mode


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
