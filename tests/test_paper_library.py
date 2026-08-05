"""Paper Library CRUD."""

from __future__ import annotations

from fastapi.testclient import TestClient

from botdraw.api.main import app
from botdraw.paper import USER_DIR, load_paper

client = TestClient(app)


def test_api_papers_list():
    r = client.get("/api/papers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert "natural-cream" in ids


def test_api_paper_save_and_delete_user():
    body = {
        "id": "test-user-cream",
        "name": "Test Cream",
        "color_hex": "#eee0cc",
        "finish": "matte",
        "size_hint": "A4",
        "notes": "pytest",
    }
    r = client.post("/api/papers/save", json=body)
    assert r.status_code == 200
    assert r.json()["id"] == "test-user-cream"
    assert load_paper("test-user-cream").color_hex == "#eee0cc"
    d = client.delete("/api/papers/test-user-cream")
    assert d.status_code == 200
    assert not (USER_DIR / "test-user-cream.json").exists()


def test_api_paper_delete_preset_forbidden():
    r = client.delete("/api/papers/natural-cream")
    assert r.status_code == 403
