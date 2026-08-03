"""LettersBot draft/vectorize fast path."""

from fastapi.testclient import TestClient

from botdraw.api.main import app


client = TestClient(app)


def test_letter_template_fast_path_skips_llm_and_optimize():
    r = client.post(
        "/api/letters/draft",
        json={
            "names": "A & B",
            "use_llm": False,
            "optimize": False,
            "highlight": False,
            "body": "HELLO WORLD",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["draft"]["source"] == "provided"
    assert data["settings"]["timing_s"]["vectorize"] < 2.0
    assert data["settings"]["draft_source"] == "provided"
    assert data["emulator"]["segments"]


def test_letter_template_draft_without_body():
    r = client.post(
        "/api/letters/draft",
        json={"names": "Aanya & Kabir", "use_llm": False, "optimize": False, "highlight": True},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["draft"]["source"] == "template"
    assert data["settings"]["timing_s"]["draft"] < 1.0
