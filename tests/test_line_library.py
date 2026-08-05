"""Line Library CRUD + preview."""

from __future__ import annotations

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.lines import USER_DIR, load_line

client = TestClient(app)


def test_api_lines_list():
    r = client.get("/api/lines")
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()}
    assert "solid" in ids


def test_api_line_preview():
    r = client.get("/api/lines/solid/preview.svg")
    assert r.status_code == 200
    assert "svg" in r.headers.get("content-type", "")
    assert "<svg" in r.text


def test_api_line_save_and_delete_user():
    body = {
        "id": "test-user-wave",
        "name": "Test Wave",
        "line_type": "wave",
        "line_spacing_mm": 1.4,
        "pattern_period_mm": 2.5,
        "pattern_amplitude_mm": 0.9,
        "dash_mm": 2.0,
        "gap_mm": 1.2,
        "ornament_target": "all",
        "notes": "pytest",
    }
    r = client.post("/api/lines/save", json=body)
    assert r.status_code == 200
    assert r.json()["id"] == "test-user-wave"
    assert load_line("test-user-wave").line_type == "wave"
    d = client.delete("/api/lines/test-user-wave")
    assert d.status_code == 200
    assert not (USER_DIR / "test-user-wave.json").exists()


def test_api_line_delete_preset_forbidden():
    r = client.delete("/api/lines/solid")
    assert r.status_code == 403
