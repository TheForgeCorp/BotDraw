"""
Neural detection layer for portrait ingest.

Three small pre-trained ONNX models replace the hand-tuned classical
detectors as the source of edges and subject isolation:

- ``u2net_portrait``: APDrawing-trained U2-Net — photo → artist-style
  portrait line raster (the edge channel source).
- ``u2net_human_seg``: person matting — subject/background isolation
  (replaces the focus/bokeh heuristics).
- ``face_parsing``: BiSeNet on CelebAMask-HQ — per-pixel region labels
  (skin/hair/eyes/glasses/lips/cloth) for crops and stroke policy.

All inference is CPU (onnxruntime), ~2 s total per photo at 512 px.
Weights are cached under ``BOTDRAW_MODELS_DIR`` (default ``~/.botdraw/models``)
and fetched explicitly via ``botdraw models fetch`` — ingest never downloads.
When onnxruntime or weights are missing, callers fall back to the classic
pipeline.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

MODEL_SPECS: dict[str, dict[str, str]] = {
    "u2net_portrait": {
        "file": "u2net_portrait_bgr.onnx",
        "url": "https://github.com/Akiya-Research-Institute/U-2-Net-Portrait-on-UE4/releases/download/v0.1/U2Net_Protrait_1x512x512x3xBGRxByte.onnx",
        "sha256": "d3a1fd91bfa9c4c191a18df038bd512c2746025de8e7e5615085c86f51289f63",
    },
    "u2net_human_seg": {
        "file": "u2net_human_seg.onnx",
        "url": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx",
        "sha256": "01eb6a29a5c4d8edb30b56adad9bb3a2a0535338e480724a213e0acfd2d1c73c",
    },
    "face_parsing": {
        "file": "face_parsing_resnet18.onnx",
        "url": "https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx",
        "sha256": "0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f",
    },
}

# CelebAMask-HQ label groups
FACE_CLASSES = frozenset({1, 2, 3, 4, 5, 6, 10, 11, 12, 13})  # skin..lips + glasses
HAIR_CLASSES = frozenset({17, 18})
FEATURE_CLASSES = frozenset({2, 3, 4, 5, 6, 10, 11, 12, 13})  # brows/eyes/glasses/nose/mouth

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_sessions: dict[str, Any] = {}


def models_dir() -> Path:
    return Path(os.environ.get("BOTDRAW_MODELS_DIR", "~/.botdraw/models")).expanduser()


def model_path(name: str) -> Path:
    return models_dir() / MODEL_SPECS[name]["file"]


def model_status() -> dict[str, bool]:
    return {name: model_path(name).exists() for name in MODEL_SPECS}


def fetch_models(names: list[str] | None = None, *, force: bool = False) -> dict[str, str]:
    """Download model weights (CLI path — ingest never calls this)."""
    import httpx

    results: dict[str, str] = {}
    target = models_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name in names or list(MODEL_SPECS):
        spec = MODEL_SPECS[name]
        dst = target / spec["file"]
        if dst.exists() and not force:
            results[name] = "present"
            continue
        tmp = dst.with_suffix(".part")
        with httpx.stream("GET", spec["url"], follow_redirects=True, timeout=120.0) as r:
            r.raise_for_status()
            h = hashlib.sha256()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
        if h.hexdigest() != spec["sha256"]:
            tmp.unlink(missing_ok=True)
            results[name] = "checksum-mismatch"
            continue
        tmp.rename(dst)
        results[name] = "downloaded"
    return results


def _get_session(name: str):
    if name in _sessions:
        return _sessions[name]
    path = model_path(name)
    if not path.exists():
        return None
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    sess = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
    _sessions[name] = sess
    return sess


def neural_available() -> bool:
    """True when onnxruntime + the portrait and matting weights are present."""
    return _get_session("u2net_portrait") is not None and _get_session("u2net_human_seg") is not None


def shadow_lift(rgb: np.ndarray) -> np.ndarray:
    """Percentile autocontrast + gamma lift; the portrait model was trained on
    well-lit studio crops, so dim photos need exposure normalization first."""
    lum = rgb.mean(axis=2)
    p2, p98 = np.percentile(lum, [2, 98])
    scaled = np.clip((rgb - p2) / max(p98 - p2, 1e-3) * 255.0, 0, 255)
    med = float(np.median(scaled.mean(axis=2)))
    if med < 110.0:
        gamma = float(np.clip(np.log(0.5) / np.log(max(med, 1.0) / 255.0), 1.0, 2.2))
        scaled = (np.clip(scaled / 255.0, 0, 1) ** (1.0 / gamma)) * 255.0
    return scaled.astype(np.float32)


def _imagenet_input(rgb: np.ndarray, size: int) -> np.ndarray:
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize(
        (size, size), Image.Resampling.LANCZOS
    )
    x = np.asarray(img, dtype=np.float32) / 255.0
    x = (x - _IMAGENET_MEAN) / _IMAGENET_STD
    return x.transpose(2, 0, 1)[None].astype(np.float32)


def subject_mask(rgb: np.ndarray) -> np.ndarray | None:
    """Person matte in [0..1] at source resolution."""
    sess = _get_session("u2net_human_seg")
    if sess is None:
        return None
    x = _imagenet_input(rgb, 320)
    d1 = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    d1 = (d1 - d1.min()) / max(float(d1.max() - d1.min()), 1e-6)
    m = Image.fromarray((d1 * 255).astype(np.uint8)).resize(
        (rgb.shape[1], rgb.shape[0]), Image.Resampling.BILINEAR
    )
    return np.asarray(m, dtype=np.float32) / 255.0


def face_parse(rgb: np.ndarray) -> np.ndarray | None:
    """CelebAMask-HQ labels (uint8) at source resolution."""
    sess = _get_session("face_parsing")
    if sess is None:
        return None
    x = _imagenet_input(rgb, 512)
    logits = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
    labels = np.argmax(logits, axis=0).astype(np.uint8)
    lab = Image.fromarray(labels).resize(
        (rgb.shape[1], rgb.shape[0]), Image.Resampling.NEAREST
    )
    return np.asarray(lab, dtype=np.uint8)


def face_crop_box(
    labels: np.ndarray | None, shape: tuple[int, int], expand: float = 1.55
) -> tuple[int, int, int]:
    """Square (x0, y0, side) around face+hair labels; center-square fallback."""
    h, w = shape
    if labels is not None:
        m = np.isin(labels, list(FACE_CLASSES | HAIR_CLASSES))
        ys, xs = np.nonzero(m)
        if ys.size >= 100:
            cy, cx = float(ys.mean()), float(xs.mean())
            side = int(max(ys.max() - ys.min(), xs.max() - xs.min()) * expand)
            side = min(max(side, 64), min(h, w))
            x0 = int(np.clip(cx - side / 2, 0, w - side))
            y0 = int(np.clip(cy - side / 2, 0, h - side))
            return x0, y0, side
    side = min(h, w)
    return (w - side) // 2, (h - side) // 2, side


def portrait_line_ink(rgb: np.ndarray, box: tuple[int, int, int]) -> np.ndarray | None:
    """Artist-line ink map [0..1] at source resolution (zero outside the crop)."""
    sess = _get_session("u2net_portrait")
    if sess is None:
        return None
    x0, y0, side = box
    crop = rgb[y0 : y0 + side, x0 : x0 + side]
    img = Image.fromarray(np.clip(crop, 0, 255).astype(np.uint8)).resize(
        (512, 512), Image.Resampling.LANCZOS
    )
    bgr = np.asarray(img, dtype=np.uint8)[:, :, ::-1]
    out = sess.run(None, {sess.get_inputs()[0].name: bgr[None]})[0]
    ink = 1.0 - out.astype(np.float32) / 255.0  # model emits white-paper drawing
    full = np.zeros(rgb.shape[:2], dtype=np.float32)
    ink_img = Image.fromarray((ink * 255).astype(np.uint8)).resize(
        (side, side), Image.Resampling.LANCZOS
    )
    full[y0 : y0 + side, x0 : x0 + side] = np.asarray(ink_img, dtype=np.float32) / 255.0
    return full


def portrait_line_ink_letterbox(rgb: np.ndarray) -> np.ndarray | None:
    """Whole-frame pass: pad to square with white, infer, unpad."""
    sess = _get_session("u2net_portrait")
    if sess is None:
        return None
    h, w = rgb.shape[:2]
    side = max(h, w)
    canvas = np.full((side, side, 3), 255.0, dtype=np.float32)
    oy, ox = (side - h) // 2, (side - w) // 2
    canvas[oy : oy + h, ox : ox + w] = rgb
    img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)).resize(
        (512, 512), Image.Resampling.LANCZOS
    )
    bgr = np.asarray(img, dtype=np.uint8)[:, :, ::-1]
    out = sess.run(None, {sess.get_inputs()[0].name: bgr[None]})[0]
    ink = 1.0 - out.astype(np.float32) / 255.0
    ink_img = Image.fromarray((ink * 255).astype(np.uint8)).resize(
        (side, side), Image.Resampling.LANCZOS
    )
    full = np.asarray(ink_img, dtype=np.float32)[oy : oy + h, ox : ox + w] / 255.0
    return np.ascontiguousarray(full)


def neural_portrait_pack(rgb: np.ndarray) -> dict[str, Any] | None:
    """
    Run the full neural detection pass. Returns None when unavailable.

    Keys: ``ink`` (line raster [0..1]), ``mask`` (person matte [0..1]),
    ``labels`` (parse labels or None), ``box`` (face crop), ``lifted`` (rgb).
    """
    if not neural_available():
        return None
    lifted = shadow_lift(rgb)
    mask = subject_mask(rgb)
    labels = face_parse(lifted)
    box = face_crop_box(labels, rgb.shape[:2])
    # Widen the crop to cover the whole subject so shoulders/hair aren't cut
    # at the model's paste boundary (the model handles head-dominant framing
    # fine; it degrades only when the head is small).
    if mask is not None:
        m = mask > 0.5
        if 0.05 < float(m.mean()):
            ys, xs = np.nonzero(m)
            h, w = rgb.shape[:2]
            side = int(max(ys.max() - ys.min(), xs.max() - xs.min()) * 1.05)
            side = min(max(side, box[2]), min(h, w))
            cx = float(xs.mean())
            cy = float(ys.mean())
            x0 = int(np.clip(cx - side / 2, 0, w - side))
            y0 = int(np.clip(cy - side / 2, 0, h - side))
            box = (x0, y0, side)
    ink = portrait_line_ink(lifted, box)
    if ink is None or mask is None:
        return None
    # Second whole-frame pass fills coverage the square crop misses
    # (shoulders/hair outside the box); face detail comes from the crop pass.
    if box[2] < min(rgb.shape[0], rgb.shape[1]) or box[2] < max(rgb.shape[0], rgb.shape[1]):
        ink_full = portrait_line_ink_letterbox(lifted)
        if ink_full is not None:
            ink = np.maximum(ink, ink_full)
    # Gate lines to the subject; soft edge avoids halo cuts
    ink = ink * np.clip(mask * 1.4, 0.0, 1.0)
    return {"ink": ink, "mask": mask, "labels": labels, "box": box, "lifted": lifted}
