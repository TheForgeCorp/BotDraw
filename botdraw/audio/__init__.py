"""Audio / voice / MIDI → multicolor vector layers."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, Polyline, StyleParams, paper_dims
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, load_palette


def _read_wav_mono(path: str | Path, max_samples: int = 8000) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        n = wf.getnframes()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        raw = wf.readframes(n)
    if sampwidth == 2:
        fmt = f"<{len(raw)//2}h"
        data = np.array(struct.unpack(fmt, raw), dtype=np.float32)
    else:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if len(data) > max_samples:
        idx = np.linspace(0, len(data) - 1, max_samples).astype(int)
        data = data[idx]
    peak = np.max(np.abs(data)) or 1.0
    return data / peak


def synth_tone(seconds: float = 1.5, sr: int = 8000) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return 0.6 * np.sin(2 * math.pi * 220 * t) + 0.3 * np.sin(2 * math.pi * 330 * t)


def audio_to_layered(
    samples: np.ndarray,
    *,
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    orientation: Orientation = Orientation.PORTRAIT,
    seed: int = 11,
) -> LayeredSVG:
    palette = load_palette(palette_id)
    pens = ink_pens(palette)
    pw, ph = paper_dims(paper, orientation)
    margin = 15
    usable_w = pw - 2 * margin
    usable_h = ph - 2 * margin
    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    # Waveform ribbon
    pts = []
    for i, s in enumerate(samples):
        x = margin + usable_w * (i / max(1, len(samples) - 1))
        y = ph / 2 + s * usable_h * 0.35
        pts.append((x, y))
    buckets[pens[0].id].append(Polyline(points=pts, pen_id=pens[0].id))
    # Envelope bands in other pens
    win = max(8, len(samples) // 40)
    env_pts = []
    for i in range(0, len(samples), win):
        chunk = samples[i : i + win]
        amp = float(np.mean(np.abs(chunk)))
        x = margin + usable_w * (i / max(1, len(samples) - 1))
        env_pts.append((x, ph / 2 - amp * usable_h * 0.45))
    if len(env_pts) >= 2 and len(pens) > 1:
        buckets[pens[1].id].append(Polyline(points=env_pts, pen_id=pens[1].id))
    # Beat-ish ticks from local peaks
    if len(pens) > 2:
        ticks = []
        for i in range(1, len(samples) - 1):
            if samples[i] > samples[i - 1] and samples[i] > samples[i + 1] and samples[i] > 0.6:
                x = margin + usable_w * (i / max(1, len(samples) - 1))
                ticks.append(Polyline(points=[(x, ph / 2 - 8), (x, ph / 2 + 8)], pen_id=pens[2].id))
        buckets[pens[2].id].extend(ticks[:80])
    passes = [make_pass(f"audio-{pid}", f"Audio {pid}", pid, polys) for pid, polys in buckets.items() if polys]
    return LayeredSVG(width_mm=pw, height_mm=ph, passes=passes, seed=seed, meta={"style": "audio"})


def render_audio_file(path: str | Path, **kwargs) -> LayeredSVG:
    return audio_to_layered(_read_wav_mono(path), **kwargs)


def render_demo_tone(**kwargs) -> LayeredSVG:
    return audio_to_layered(synth_tone(), **kwargs)
