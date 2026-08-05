"""Synthetic demo sensor datasets for R&D Lab (no hardware required)."""

from __future__ import annotations

import math

import numpy as np

from botdraw.data.map import SensorRecord

DEMO_IDS = ("temperature", "gps_walk", "gforce")


def list_demos() -> list[dict]:
    return [
        {
            "id": "temperature",
            "label": "Daily mean temperature",
            "kind": "series",
            "unit": "°C",
            "description": "Synthetic year of daily mean temps — seasonal sine + weather noise",
            "default_mode": "ribbon",
            "suggested_modes": ["ribbon", "mirror", "radial", "spiral", "mandala"],
        },
        {
            "id": "gps_walk",
            "label": "GPS walk path",
            "kind": "path",
            "unit": "deg",
            "description": "Synthetic neighborhood walk (lon/lat) — loops and meanders",
            "default_mode": "path",
            "suggested_modes": ["path", "ribbon", "spiral", "mandala"],
        },
        {
            "id": "gforce",
            "label": "G-force log",
            "kind": "vectors",
            "unit": "g",
            "description": "Synthetic 3-axis accelerometer burst — rest, bump, corner",
            "default_mode": "ribbon",
            "suggested_modes": ["ribbon", "mirror", "radial", "spiral", "mandala"],
        },
    ]


def load_demo(demo_id: str) -> SensorRecord:
    key = str(demo_id).strip().lower().replace("-", "_")
    if key not in DEMO_IDS:
        raise ValueError(f"unknown demo {demo_id!r}; choose from {DEMO_IDS}")
    if key == "temperature":
        return _demo_temperature()
    if key == "gps_walk":
        return _demo_gps_walk()
    return _demo_gforce()


def _demo_temperature() -> SensorRecord:
    """365 daily means: seasonal curve + weekly weather + diurnal-ish noise."""
    days = np.arange(365, dtype=np.float64)
    seasonal = 12.0 + 10.0 * np.sin(2 * math.pi * (days - 80) / 365.0)
    rng = np.random.default_rng(2026)
    weather = rng.normal(0.0, 2.2, size=365)
    # mild autocorrelation
    for i in range(1, 365):
        weather[i] = 0.65 * weather[i - 1] + 0.35 * weather[i]
    vals = seasonal + weather
    return SensorRecord(
        kind="series",
        label="Daily mean temperature",
        unit="°C",
        values=vals,
        meta={"demo": "temperature", "n_days": 365},
    )


def _demo_gps_walk() -> SensorRecord:
    """Closed-ish walk around a fake park block near (lon, lat)."""
    n = 280
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    # Rounded square with a figure-eight meander
    lon0, lat0 = -122.4194, 37.7749
    scale = 0.004
    lon = lon0 + scale * (0.9 * np.cos(t) + 0.15 * np.cos(3 * t) + 0.08 * np.sin(5 * t))
    lat = lat0 + scale * (0.7 * np.sin(t) + 0.2 * np.sin(2 * t) + 0.05 * np.cos(4 * t))
    # add a spur
    spur_t = np.linspace(0, 1, 40)
    spur_lon = lon[-1] + spur_t * 0.0015
    spur_lat = lat[-1] + spur_t * 0.0004 * np.sin(spur_t * math.pi)
    pts = np.column_stack(
        [
            np.concatenate([lon, spur_lon, spur_lon[::-1]]),
            np.concatenate([lat, spur_lat, spur_lat[::-1]]),
        ]
    )
    return SensorRecord(
        kind="path",
        label="GPS walk path",
        unit="deg",
        points=pts,
        meta={"demo": "gps_walk", "origin": [lon0, lat0]},
    )


def _demo_gforce() -> SensorRecord:
    """ax, ay, az over ~8s at 50 Hz: idle → bump → corner → settle."""
    sr = 50
    seconds = 8.0
    n = int(sr * seconds)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(7)
    ax = rng.normal(0, 0.03, size=n)
    ay = rng.normal(0, 0.03, size=n)
    az = 1.0 + rng.normal(0, 0.02, size=n)
    # bump at t=2.2
    bump = np.exp(-((t - 2.2) ** 2) / (2 * 0.04**2))
    ax += 0.9 * bump
    az += 0.35 * bump
    # cornering lateral at t=4.5–5.5
    corner = ((t >= 4.5) & (t <= 5.5)).astype(np.float64)
    envelope = np.sin(math.pi * np.clip((t - 4.5) / 1.0, 0, 1))
    ay += 0.55 * corner * envelope
    ax -= 0.15 * corner * envelope
    samples = np.column_stack([ax, ay, az])
    return SensorRecord(
        kind="vectors",
        label="G-force log",
        unit="g",
        samples=samples,
        meta={"demo": "gforce", "sr_hz": sr, "seconds": seconds},
    )
