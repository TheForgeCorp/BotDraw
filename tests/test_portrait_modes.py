"""Portrait preprocess and image_mode wiring."""

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from botdraw.api.main import app
from botdraw.styles.image_utils import load_image_array, synthetic_portrait


client = TestClient(app)


def _tmp_face(path: Path):
    Image.fromarray(synthetic_portrait(96).astype(np.uint8)).save(path)


def test_image_modes_differ():
    p = Path("/tmp/botdraw-face.png")
    _tmp_face(p)
    photo = load_image_array(p, 96, mode="photo")
    drawing = load_image_array(p, 96, mode="drawing")
    assert photo.shape == drawing.shape
    assert not np.allclose(photo, drawing)


def test_render_with_image_mode_extra():
    r = client.post(
        "/api/render",
        json={
            "app": "portraitbot",
            "style_id": "portrait_linework",
            "palette_id": "default-6",
            "paper": "A5",
            "quality": "booth-fast",
            "seed": 3,
            "density": 0.8,
            "params_extra": {"image_mode": "sketch"},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["emulator"]["segments"]
    assert data["layers"]["pass_count"] >= 1
