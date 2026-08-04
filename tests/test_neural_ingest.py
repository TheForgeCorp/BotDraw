"""Neural portrait ingest: unit tests with stubbed sessions + gated integration."""
from __future__ import annotations

import numpy as np
import pytest

from botdraw.portrait import neural


def _synthetic_rgb(size: int = 240) -> np.ndarray:
    rng = np.random.default_rng(3)
    rgb = np.full((size, size, 3), 235.0, dtype=np.float32)
    yy, xx = np.mgrid[0:size, 0:size]
    face = ((yy - size * 0.45) ** 2 + (xx - size * 0.5) ** 2) < (size * 0.25) ** 2
    rgb[face] = 180.0
    rgb += rng.normal(0, 4, rgb.shape)
    return np.clip(rgb, 0, 255).astype(np.float32)


def test_shadow_lift_brightens_dim_photo():
    dim = np.clip(_synthetic_rgb() * 0.25, 0, 255)
    lifted = neural.shadow_lift(dim)
    assert float(np.median(lifted)) > float(np.median(dim)) * 1.5
    assert lifted.min() >= 0.0 and lifted.max() <= 255.0


def test_shadow_lift_keeps_bright_photo_stable():
    bright = _synthetic_rgb()
    lifted = neural.shadow_lift(bright)
    # Autocontrast only — median should stay in the same ballpark
    assert abs(float(np.median(lifted)) - float(np.median(bright))) < 60.0


def test_face_crop_box_falls_back_to_center_square():
    box = neural.face_crop_box(None, (300, 200))
    assert box == (0, 50, 200)


def test_face_crop_box_centers_on_labels():
    labels = np.zeros((200, 200), dtype=np.uint8)
    labels[40:120, 60:140] = 1  # skin blob
    x0, y0, side = neural.face_crop_box(labels, (200, 200))
    assert side >= 80
    cx = x0 + side / 2
    cy = y0 + side / 2
    assert abs(cx - 100) < 20 and abs(cy - 80) < 25


def test_models_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTDRAW_MODELS_DIR", str(tmp_path))
    assert neural.models_dir() == tmp_path
    status = neural.model_status()
    assert set(status) == set(neural.MODEL_SPECS)
    assert not any(status.values())


def test_neural_unavailable_without_weights(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTDRAW_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(neural, "_sessions", {})
    assert not neural.neural_available()
    assert neural.neural_portrait_pack(_synthetic_rgb()) is None


class _StubInput:
    name = "input"


class _StubSession:
    """Mimics the three ONNX sessions closely enough for the pack pipeline."""

    def __init__(self, kind: str):
        self.kind = kind

    def get_inputs(self):
        return [_StubInput()]

    def run(self, _outs, feeds):
        x = feeds["input"]
        if self.kind == "u2net_human_seg":
            d1 = np.zeros((1, 1, 320, 320), dtype=np.float32)
            d1[0, 0, 40:, :] = 1.0  # subject fills most of the frame
            return [d1]
        if self.kind == "face_parsing":
            logits = np.zeros((1, 19, 512, 512), dtype=np.float32)
            logits[0, 1, 100:400, 100:400] = 5.0  # skin blob
            return [logits]
        # portrait: dark band of "drawing" in the middle, white elsewhere
        out = np.full((512, 512), 255, dtype=np.uint8)
        out[200:280, :] = 10
        return [out]


def test_neural_portrait_pack_with_stub_sessions(monkeypatch):
    def fake_get_session(name):
        return _StubSession(name)

    monkeypatch.setattr(neural, "_get_session", fake_get_session)
    rgb = _synthetic_rgb(320)
    pack = neural.neural_portrait_pack(rgb)
    assert pack is not None
    assert pack["ink"].shape == rgb.shape[:2]
    assert pack["mask"].shape == rgb.shape[:2]
    assert pack["labels"].shape == rgb.shape[:2]
    # Dark band from the stub portrait model must land as ink > 0.5 somewhere
    assert float(pack["ink"].max()) > 0.5
    x0, y0, side = pack["box"]
    assert side > 0 and x0 >= 0 and y0 >= 0


def test_ingest_classic_fallback_records_line_source(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTDRAW_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(neural, "_sessions", {})
    from botdraw.core.models import QualityPreset
    from botdraw.portrait.ingest import ingest_portrait

    pv = ingest_portrait(
        image_array=_synthetic_rgb(),
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        line_source="neural",
    )
    assert pv.meta.get("line_source") == "classic"


@pytest.mark.skipif(not neural.neural_available(), reason="model weights not installed")
def test_ingest_neural_end_to_end():
    from botdraw.core.models import QualityPreset
    from botdraw.portrait.ingest import ingest_portrait

    pv = ingest_portrait(
        image_array=_synthetic_rgb(),
        mode="photo",
        quality=QualityPreset.BOOTH_FAST,
        paper="A5",
        auto_frame=False,
        line_source="neural",
    )
    assert pv.meta.get("line_source") == "neural"
    assert pv.meta.get("edge_extractor") == "neural_lines"
    assert pv.tone_codes is not None
