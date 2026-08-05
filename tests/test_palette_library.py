"""Palette Library CRUD (save + delete user palettes)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.palettes import USER_DIR, load_palette

client = TestClient(app)


def test_api_palettes_list():
    r = client.get("/api/palettes")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert "default-6" in ids


def test_api_palette_save_and_delete_user():
    body = {
        "id": "test-user-palette",
        "name": "Test Palette",
        "paper_notes": "pytest",
        "pens": [
            {
                "id": "ink",
                "name": "Ink",
                "color_hex": "#222222",
                "profile": {"width_mm": 0.4, "opacity": 1.0, "nib_type": "fineliner"},
            }
        ],
    }
    r = client.post("/api/palettes/save", json=body)
    assert r.status_code == 200
    assert r.json()["id"] == "test-user-palette"
    assert load_palette("test-user-palette").pens[0].color_hex == "#222222"
    d = client.delete("/api/palettes/test-user-palette")
    assert d.status_code == 200
    assert not (USER_DIR / "test-user-palette.json").exists()


def test_api_palette_delete_preset_forbidden():
    r = client.delete("/api/palettes/default-6")
    assert r.status_code == 403
