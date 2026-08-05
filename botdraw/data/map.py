"""Map SensorRecord → LayeredSVG with symmetry / pattern modes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from botdraw.core.models import LayeredSVG, Orientation, PaperSize, Polyline, paper_dims
from botdraw.core.svg import make_pass
from botdraw.palettes import ink_pens, load_palette
from botdraw.styles.geom import margin_box

Kind = Literal["series", "path", "vectors"]
Mode = Literal["ribbon", "mirror", "radial", "spiral", "path", "mandala"]

MODES: tuple[Mode, ...] = ("ribbon", "mirror", "radial", "spiral", "path", "mandala")

_GOLDEN = 137.5


@dataclass
class SensorRecord:
    kind: Kind
    label: str = "sensor"
    unit: str | None = None
    values: np.ndarray | None = None  # 1D series
    points: np.ndarray | None = None  # Nx2 path
    samples: np.ndarray | None = None  # Nx3 vectors
    meta: dict = field(default_factory=dict)

    def series_values(self) -> np.ndarray:
        """Normalize any kind into a 1D series for pattern modes."""
        if self.kind == "series" and self.values is not None:
            return np.asarray(self.values, dtype=np.float64).ravel()
        if self.kind == "vectors" and self.samples is not None:
            s = np.asarray(self.samples, dtype=np.float64)
            return np.linalg.norm(s, axis=1)
        if self.kind == "path" and self.points is not None:
            p = np.asarray(self.points, dtype=np.float64)
            if len(p) < 2:
                return np.zeros(1)
            d = np.diff(p, axis=0)
            step = np.hypot(d[:, 0], d[:, 1])
            return np.concatenate([[0.0], np.cumsum(step)])
        raise ValueError(f"record has no drawable series (kind={self.kind})")

    def path_points(self) -> np.ndarray:
        if self.kind == "path" and self.points is not None:
            return np.asarray(self.points, dtype=np.float64)
        if self.kind == "vectors" and self.samples is not None:
            s = np.asarray(self.samples, dtype=np.float64)
            return s[:, :2]
        # series → (i, value) path
        v = self.series_values()
        idx = np.arange(len(v), dtype=np.float64)
        return np.column_stack([idx, v])


def _downsample(arr: np.ndarray, max_n: int) -> np.ndarray:
    n = len(arr)
    if n <= max_n:
        return arr
    idx = np.linspace(0, n - 1, max_n).astype(int)
    return arr[idx]


def _normalize(vals: np.ndarray, *, center: bool = True) -> np.ndarray:
    v = np.asarray(vals, dtype=np.float64).ravel()
    v = v[np.isfinite(v)]
    if v.size == 0:
        return v
    if center:
        v = v - np.mean(v)
    peak = float(np.max(np.abs(v))) or 1.0
    return v / peak


def _fit_path(pts: np.ndarray, box: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Fit Nx2 points into margin box, preserving aspect."""
    x0, y0, x1, y1 = box
    usable_w = max(1.0, x1 - x0)
    usable_h = max(1.0, y1 - y0)
    p = np.asarray(pts, dtype=np.float64)
    if len(p) < 2:
        return []
    mn = p.min(axis=0)
    mx = p.max(axis=0)
    span = mx - mn
    span = np.where(span < 1e-9, 1.0, span)
    scale = min(usable_w / span[0], usable_h / span[1])
    mid = (mn + mx) / 2
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    out = []
    for x, y in p:
        out.append((cx + (x - mid[0]) * scale, cy - (y - mid[1]) * scale))
    return out


def default_mode(kind: Kind) -> Mode:
    if kind == "path":
        return "path"
    return "ribbon"


def data_to_layered(
    record: SensorRecord,
    *,
    mode: Mode | str | None = None,
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    orientation: Orientation = Orientation.PORTRAIT,
    seed: int = 42,
    density: float = 1.0,
    folds: int = 6,
) -> LayeredSVG:
    """Convert a sensor record into multi-pen LayeredSVG art."""
    mode_s = str(mode or default_mode(record.kind)).strip().lower()
    if mode_s not in MODES:
        raise ValueError(f"unknown mode {mode_s!r}; choose from {MODES}")
    mode_e: Mode = mode_s  # type: ignore[assignment]

    palette = load_palette(palette_id)
    pens = ink_pens(palette)
    pw, ph = paper_dims(paper, orientation)
    box = margin_box(pw, ph, margin=14.0)
    x0, y0, x1, y1 = box
    usable_w = x1 - x0
    usable_h = y1 - y0
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    dens = max(0.4, min(2.5, float(density)))
    max_pts = int(1200 * dens)

    buckets: dict[str, list[Polyline]] = {p.id: [] for p in pens}
    p0 = pens[0].id
    p1 = pens[1].id if len(pens) > 1 else p0
    p2 = pens[2].id if len(pens) > 2 else p0

    if mode_e == "path":
        pts = _downsample(record.path_points(), max_pts)
        fitted = _fit_path(pts, box)
        if len(fitted) >= 2:
            buckets[p0].append(Polyline(points=fitted, pen_id=p0))
            buckets[p1].append(
                Polyline(points=[(fitted[0][0] - 2, fitted[0][1]), (fitted[0][0] + 2, fitted[0][1])], pen_id=p1)
            )
            buckets[p2].append(
                Polyline(points=[(fitted[-1][0], fitted[-1][1] - 2), (fitted[-1][0], fitted[-1][1] + 2)], pen_id=p2)
            )
    elif mode_e == "ribbon":
        _draw_ribbon(record, buckets, pens, box, max_pts)
    elif mode_e == "mirror":
        _draw_mirror(record, buckets, pens, box, max_pts)
    elif mode_e == "radial":
        _draw_radial(record, buckets, pens, cx, cy, min(usable_w, usable_h) * 0.45, max_pts)
    elif mode_e == "spiral":
        _draw_spiral(record, buckets, pens, cx, cy, min(usable_w, usable_h) * 0.46, max_pts)
    elif mode_e == "mandala":
        _draw_mandala(record, buckets, pens, cx, cy, min(usable_w, usable_h) * 0.42, max_pts, folds=folds)

    # Vector components as extra faint ribbons when applicable
    if record.kind == "vectors" and record.samples is not None and mode_e in ("ribbon", "mirror"):
        _draw_vector_overlays(record, buckets, pens, box, max_pts)

    passes = [
        make_pass(f"sensor-{pid}", f"Sensor {pid}", pid, polys)
        for pid, polys in buckets.items()
        if polys
    ]
    return LayeredSVG(
        width_mm=pw,
        height_mm=ph,
        passes=passes,
        seed=seed,
        meta={
            "style": "sensor",
            "library": "rdlab",
            "kind": record.kind,
            "mode": mode_e,
            "label": record.label,
            "unit": record.unit,
            "n": int(
                len(record.values)
                if record.values is not None
                else len(record.points)
                if record.points is not None
                else len(record.samples)
                if record.samples is not None
                else 0
            ),
            "folds": folds if mode_e == "mandala" else None,
            "strokes": sum(len(p.polylines) for p in passes),
        },
    )


def _draw_ribbon(record, buckets, pens, box, max_pts) -> None:
    x0, y0, x1, y1 = box
    usable_w = x1 - x0
    usable_h = y1 - y0
    cy = (y0 + y1) / 2
    vals = _downsample(_normalize(record.series_values()), max_pts)
    if len(vals) < 2:
        return
    p0 = pens[0].id
    pts = []
    for i, s in enumerate(vals):
        x = x0 + usable_w * (i / (len(vals) - 1))
        y = cy + float(s) * usable_h * 0.42
        pts.append((x, y))
    buckets[p0].append(Polyline(points=pts, pen_id=p0))
    # envelope
    if len(pens) > 1:
        win = max(4, len(vals) // 36)
        env = []
        for i in range(0, len(vals), win):
            chunk = vals[i : i + win]
            amp = float(np.mean(np.abs(chunk)))
            x = x0 + usable_w * (i / (len(vals) - 1))
            env.append((x, cy - amp * usable_h * 0.48))
        if len(env) >= 2:
            buckets[pens[1].id].append(Polyline(points=env, pen_id=pens[1].id))


def _draw_mirror(record, buckets, pens, box, max_pts) -> None:
    x0, y0, x1, y1 = box
    usable_w = x1 - x0
    usable_h = y1 - y0
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    vals = _downsample(_normalize(record.series_values()), max_pts)
    if len(vals) < 2:
        return
    half_w = usable_w * 0.48
    left = []
    right = []
    for i, s in enumerate(vals):
        t = i / (len(vals) - 1)
        y = y0 + usable_h * t
        dx = float(s) * half_w * 0.9
        left.append((cx - abs(dx), y))
        right.append((cx + abs(dx), y))
    buckets[pens[0].id].append(Polyline(points=left, pen_id=pens[0].id))
    buckets[pens[1].id if len(pens) > 1 else pens[0].id].append(
        Polyline(points=right, pen_id=pens[1].id if len(pens) > 1 else pens[0].id)
    )
    # spine
    if len(pens) > 2:
        buckets[pens[2].id].append(Polyline(points=[(cx, y0), (cx, y1)], pen_id=pens[2].id))


def _draw_radial(record, buckets, pens, cx, cy, radius, max_pts) -> None:
    vals = _downsample(_normalize(record.series_values(), center=False), max_pts)
    if len(vals) < 3:
        return
    # shift to [0.15, 1]
    mn, mx = float(vals.min()), float(vals.max())
    span = (mx - mn) or 1.0
    norm = 0.15 + 0.85 * (vals - mn) / span
    ring = []
    for i, r in enumerate(norm):
        th = 2 * math.pi * i / len(norm)
        ring.append((cx + math.cos(th) * r * radius, cy + math.sin(th) * r * radius))
    ring.append(ring[0])
    buckets[pens[0].id].append(Polyline(points=ring, pen_id=pens[0].id, closed=True))
    # inner guide circle
    if len(pens) > 1:
        guide = []
        for i in range(72):
            th = 2 * math.pi * i / 72
            guide.append((cx + math.cos(th) * radius * 0.2, cy + math.sin(th) * radius * 0.2))
        guide.append(guide[0])
        buckets[pens[1].id].append(Polyline(points=guide, pen_id=pens[1].id, closed=True))


def _draw_spiral(record, buckets, pens, cx, cy, radius, max_pts) -> None:
    vals = _downsample(_normalize(record.series_values(), center=False), max_pts)
    if len(vals) < 3:
        return
    mn, mx = float(vals.min()), float(vals.max())
    span = (mx - mn) or 1.0
    amp = 0.12 + 0.88 * (vals - mn) / span
    alpha = math.radians(_GOLDEN)
    pts = []
    n = len(amp)
    for i, a in enumerate(amp):
        # base Vogel radius modulated by data
        r = radius * math.sqrt(i / max(1, n - 1)) * float(a)
        th = i * alpha
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
    buckets[pens[0].id].append(Polyline(points=pts, pen_id=pens[0].id))
    # secondary reverse spiral of envelope
    if len(pens) > 1:
        env = []
        win = max(3, n // 40)
        for i in range(0, n, win):
            chunk = amp[i : i + win]
            a = float(np.mean(chunk))
            r = radius * math.sqrt(i / max(1, n - 1)) * a * 0.85
            th = i * alpha + math.pi
            env.append((cx + r * math.cos(th), cy + r * math.sin(th)))
        if len(env) >= 2:
            buckets[pens[1].id].append(Polyline(points=env, pen_id=pens[1].id))


def _draw_mandala(record, buckets, pens, cx, cy, radius, max_pts, *, folds: int) -> None:
    folds = max(3, min(16, int(folds)))
    vals = _downsample(_normalize(record.series_values()), max(32, max_pts // folds))
    if len(vals) < 4:
        return
    # Motif: half-petal from series along one sector
    motif = []
    for i, s in enumerate(vals):
        t = i / (len(vals) - 1)
        # sector-local polar: angle within sector wedge, radius from |s|
        local_th = (t - 0.5) * (2 * math.pi / folds) * 0.9
        r = radius * (0.25 + 0.75 * abs(float(s)))
        motif.append((r * math.cos(local_th), r * math.sin(local_th)))
    for k in range(folds):
        rot = 2 * math.pi * k / folds
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        pts = []
        for x, y in motif:
            pts.append((cx + x * cos_r - y * sin_r, cy + x * sin_r + y * cos_r))
        pen = pens[k % len(pens)].id
        buckets[pen].append(Polyline(points=pts, pen_id=pen))
    # outer ring
    if len(pens) > 1:
        ring = []
        for i in range(96):
            th = 2 * math.pi * i / 96
            ring.append((cx + math.cos(th) * radius, cy + math.sin(th) * radius))
        ring.append(ring[0])
        buckets[pens[-1].id].append(Polyline(points=ring, pen_id=pens[-1].id, closed=True))


def _draw_vector_overlays(record, buckets, pens, box, max_pts) -> None:
    if record.samples is None or len(pens) < 3:
        return
    x0, y0, x1, y1 = box
    usable_w = x1 - x0
    usable_h = y1 - y0
    cy = (y0 + y1) / 2
    s = _downsample(np.asarray(record.samples, dtype=np.float64), max_pts)
    for axis, pen in enumerate(pens[1:4]):
        col = _normalize(s[:, axis])
        if len(col) < 2:
            continue
        pts = []
        for i, v in enumerate(col):
            x = x0 + usable_w * (i / (len(col) - 1))
            y = cy + float(v) * usable_h * 0.18 * (axis + 1) / 3
            pts.append((x, y))
        buckets[pen.id].append(Polyline(points=pts, pen_id=pen.id))


def render_file(path: str | Path, **kwargs) -> LayeredSVG:
    from botdraw.data.parse import parse_bytes

    p = Path(path)
    return data_to_layered(parse_bytes(p.read_bytes(), filename=p.name), **kwargs)


def render_demo(demo_id: str, **kwargs) -> LayeredSVG:
    from botdraw.data.demos import load_demo

    return data_to_layered(load_demo(demo_id), **kwargs)
