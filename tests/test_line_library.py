"""Line Library storage + preview."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.lines import (
    PRESET_DIR,
    USER_DIR,
    LineStock,
    delete_line,
    list_line_ids,
    list_lines,
    load_line,
    preview_svg,
    save_line,
)

client = TestClient(app)


def test_list_lines_includes_presets():
    ids = list_line_ids()
    assert "solid" in ids
    assert "wave" in ids
    assert "railroad" in ids
    rows = list_lines()
    assert {r["id"] for r in rows} == set(ids)
    assert all("line_type" in r for r in rows)


def test_save_user_line_and_preview():
    stock = LineStock(
        id="user-test-wave",
        name="User Wave",
        line_type="wave",
        pattern_period_mm=2.5,
        pattern_amplitude_mm=1.1,
    )
    path = save_line(stock)
    assert path.exists()
    assert path.parent == USER_DIR
    loaded = load_line("user-test-wave")
    assert loaded.name == "User Wave"
    svg = preview_svg(loaded)
    assert svg
    assert "<svg" in svg
    assert "path" in svg


def test_delete_user_line():
    stock = LineStock(id="user-to-delete", name="Temp", line_type="dashed")
    save_line(stock)
    assert (USER_DIR / "user-to-delete.json").exists()
    delete_line("user-to-delete")
    assert not (USER_DIR / "user-to-delete.json").exists()


def test_cannot_delete_preset():
    assert (PRESET_DIR / "solid.json").exists() or "solid" in list_line_ids()
    load_line("solid")  # ensure seeded
    try:
        delete_line("solid")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    assert (PRESET_DIR / "solid.json").exists()


def test_api_lines_list_save_preview_delete():
    r = client.get("/api/lines")
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert "solid" in ids
    assert "zigzag" in ids

    prev = client.get("/api/lines/wave/preview.svg")
    assert prev.status_code == 200
    assert "svg" in prev.headers.get("content-type", "")
    assert prev.text and "<svg" in prev.text

    body = {
        "id": "api-user-line",
        "name": "API User",
        "line_type": "chevron",
        "pattern_period_mm": 2.8,
        "pattern_amplitude_mm": 1.0,
    }
    saved = client.post("/api/lines/save", json=body)
    assert saved.status_code == 200
    assert saved.json()["id"] == "api-user-line"

    deleted = client.delete("/api/lines/api-user-line")
    assert deleted.status_code == 200

    forbidden = client.delete("/api/lines/solid")
    assert forbidden.status_code == 403
