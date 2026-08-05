"""Parse CSV / JSON sensor payloads into SensorRecord."""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Any

import numpy as np

from botdraw.data.map import SensorRecord

_SERIES_VALUE_KEYS = ("value", "values", "temp", "temperature", "g", "magnitude", "y", "v", "metric")
_SERIES_TIME_KEYS = ("t", "time", "timestamp", "day", "date", "x", "index")
_PATH_X_KEYS = ("lon", "lng", "longitude", "x", "easting")
_PATH_Y_KEYS = ("lat", "latitude", "y", "northing")
_VEC_KEYS = (("ax", "ay", "az"), ("gx", "gy", "gz"), ("x", "y", "z"))


def _finite(arr: np.ndarray) -> np.ndarray:
    return arr[np.isfinite(arr)]


def _as_float_list(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, (int, float)):
        return [float(raw)]
    out: list[float] = []
    for v in raw:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def _pick_key(row: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    lower = {str(k).strip().lower(): k for k in row}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def parse_json_obj(obj: Any, *, label: str | None = None) -> SensorRecord:
    """Accept dict with kind/values/points/samples, or a bare list of numbers / [x,y] pairs."""
    if isinstance(obj, list):
        if not obj:
            raise ValueError("empty JSON array")
        first = obj[0]
        if isinstance(first, (int, float)):
            vals = np.asarray(_as_float_list(obj), dtype=np.float64)
            return SensorRecord(kind="series", label=label or "series", values=vals)
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            pts = []
            for row in obj:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                try:
                    x, y = float(row[0]), float(row[1])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(x) and math.isfinite(y):
                    pts.append((x, y))
            if len(pts) < 2:
                raise ValueError("need at least 2 path points")
            # Heuristic: 3+ components → vectors
            if isinstance(first, (list, tuple)) and len(first) >= 3:
                samples = []
                for row in obj:
                    if not isinstance(row, (list, tuple)) or len(row) < 3:
                        continue
                    try:
                        ax, ay, az = float(row[0]), float(row[1]), float(row[2])
                    except (TypeError, ValueError):
                        continue
                    if all(math.isfinite(v) for v in (ax, ay, az)):
                        samples.append((ax, ay, az))
                if len(samples) >= 2:
                    return SensorRecord(
                        kind="vectors",
                        label=label or "vectors",
                        samples=np.asarray(samples, dtype=np.float64),
                    )
            return SensorRecord(
                kind="path",
                label=label or "path",
                points=np.asarray(pts, dtype=np.float64),
            )
        raise ValueError("unsupported JSON array shape")

    if not isinstance(obj, dict):
        raise ValueError("JSON root must be object or array")

    kind = str(obj.get("kind") or obj.get("type") or "").strip().lower()
    lbl = label or str(obj.get("label") or obj.get("name") or kind or "sensor")
    unit = obj.get("unit")
    unit_s = str(unit) if unit is not None else None

    if kind in ("series", "timeseries", "temperature", "metric") or "values" in obj or "value" in obj:
        values = obj.get("values")
        if values is None and "value" in obj:
            values = obj["value"]
        if values is None:
            # nested data rows
            rows = obj.get("data") or obj.get("samples")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return _records_from_dicts(rows, label=lbl, unit=unit_s)
        vals = np.asarray(_as_float_list(values), dtype=np.float64)
        if vals.size < 2:
            raise ValueError("series needs at least 2 values")
        return SensorRecord(kind="series", label=lbl, unit=unit_s, values=vals)

    if kind in ("path", "gps", "track") or "points" in obj:
        pts_raw = obj.get("points") or obj.get("coords") or obj.get("coordinates")
        pts = []
        if isinstance(pts_raw, list):
            for row in pts_raw:
                if isinstance(row, dict):
                    xk = _pick_key(row, _PATH_X_KEYS)
                    yk = _pick_key(row, _PATH_Y_KEYS)
                    if xk is None or yk is None:
                        continue
                    try:
                        x, y = float(row[xk]), float(row[yk])
                    except (TypeError, ValueError):
                        continue
                elif isinstance(row, (list, tuple)) and len(row) >= 2:
                    try:
                        x, y = float(row[0]), float(row[1])
                    except (TypeError, ValueError):
                        continue
                else:
                    continue
                if math.isfinite(x) and math.isfinite(y):
                    pts.append((x, y))
        if len(pts) < 2:
            raise ValueError("path needs at least 2 points")
        return SensorRecord(kind="path", label=lbl, unit=unit_s, points=np.asarray(pts, dtype=np.float64))

    if kind in ("vectors", "gforce", "accel", "imu") or "samples" in obj:
        samples_raw = obj.get("samples") or obj.get("vectors") or obj.get("data")
        samples = []
        if isinstance(samples_raw, list):
            for row in samples_raw:
                if isinstance(row, dict):
                    for keys in _VEC_KEYS:
                        if all(k in row or k.upper() in row for k in keys):
                            try:
                                ax = float(row.get(keys[0], row.get(keys[0].upper())))
                                ay = float(row.get(keys[1], row.get(keys[1].upper())))
                                az = float(row.get(keys[2], row.get(keys[2].upper())))
                            except (TypeError, ValueError):
                                break
                            if all(math.isfinite(v) for v in (ax, ay, az)):
                                samples.append((ax, ay, az))
                            break
                elif isinstance(row, (list, tuple)) and len(row) >= 3:
                    try:
                        ax, ay, az = float(row[0]), float(row[1]), float(row[2])
                    except (TypeError, ValueError):
                        continue
                    if all(math.isfinite(v) for v in (ax, ay, az)):
                        samples.append((ax, ay, az))
        if len(samples) < 2:
            raise ValueError("vectors need at least 2 samples")
        return SensorRecord(
            kind="vectors",
            label=lbl,
            unit=unit_s,
            samples=np.asarray(samples, dtype=np.float64),
        )

    # Fall through: maybe dict-of-lists
    if "data" in obj and isinstance(obj["data"], list):
        return parse_json_obj(obj["data"], label=lbl)

    raise ValueError(f"unrecognized sensor JSON (kind={kind!r})")


def _records_from_dicts(rows: list[dict], *, label: str, unit: str | None) -> SensorRecord:
    if not rows:
        raise ValueError("empty rows")
    first = rows[0]
    # Path?
    xk = _pick_key(first, _PATH_X_KEYS)
    yk = _pick_key(first, _PATH_Y_KEYS)
    if xk and yk and _pick_key(first, _SERIES_VALUE_KEYS) is None:
        pts = []
        for row in rows:
            try:
                x, y = float(row[xk]), float(row[yk])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(x) and math.isfinite(y):
                pts.append((x, y))
        if len(pts) >= 2:
            return SensorRecord(kind="path", label=label, unit=unit, points=np.asarray(pts, dtype=np.float64))

    # Vectors?
    for keys in _VEC_KEYS:
        if all(_pick_key(first, (k,)) for k in keys):
            samples = []
            aks = [_pick_key(first, (k,)) for k in keys]
            for row in rows:
                try:
                    ax = float(row[aks[0]])  # type: ignore[index]
                    ay = float(row[aks[1]])  # type: ignore[index]
                    az = float(row[aks[2]])  # type: ignore[index]
                except (KeyError, TypeError, ValueError):
                    continue
                if all(math.isfinite(v) for v in (ax, ay, az)):
                    samples.append((ax, ay, az))
            if len(samples) >= 2:
                return SensorRecord(
                    kind="vectors",
                    label=label,
                    unit=unit,
                    samples=np.asarray(samples, dtype=np.float64),
                )

    vk = _pick_key(first, _SERIES_VALUE_KEYS)
    if vk is None:
        # last numeric column
        for k, v in first.items():
            try:
                float(v)
                vk = k
            except (TypeError, ValueError):
                continue
    if vk is None:
        raise ValueError("could not find a numeric value column")
    vals = []
    for row in rows:
        try:
            f = float(row[vk])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(f):
            vals.append(f)
    if len(vals) < 2:
        raise ValueError("series needs at least 2 values")
    return SensorRecord(kind="series", label=label, unit=unit, values=np.asarray(vals, dtype=np.float64))


def parse_csv_text(text: str, *, label: str | None = None) -> SensorRecord:
    """Parse CSV with header detection for series / path / vectors."""
    sample = text.lstrip("\ufeff")
    if not sample.strip():
        raise ValueError("empty CSV")
    reader = csv.DictReader(io.StringIO(sample))
    if reader.fieldnames:
        rows: list[dict[str, Any]] = []
        for row in reader:
            if row is None:
                continue
            cleaned = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
            if any(v not in (None, "") for v in cleaned.values()):
                rows.append(cleaned)
        if rows:
            return _records_from_dicts(rows, label=label or "csv", unit=None)

    # Headerless: try numeric columns
    reader2 = csv.reader(io.StringIO(sample))
    matrix: list[list[float]] = []
    for row in reader2:
        nums = []
        ok = True
        for cell in row:
            cell = cell.strip()
            if not cell:
                continue
            try:
                nums.append(float(cell))
            except ValueError:
                ok = False
                break
        if ok and nums:
            matrix.append(nums)
    if not matrix:
        raise ValueError("CSV has no numeric rows")
    widths = {len(r) for r in matrix}
    width = max(widths)
    if width == 1:
        vals = np.asarray([r[0] for r in matrix], dtype=np.float64)
        return SensorRecord(kind="series", label=label or "csv", values=vals)
    if width == 2:
        pts = np.asarray([[r[0], r[1]] for r in matrix if len(r) >= 2], dtype=np.float64)
        return SensorRecord(kind="path", label=label or "csv", points=pts)
    samples = np.asarray([[r[0], r[1], r[2]] for r in matrix if len(r) >= 3], dtype=np.float64)
    return SensorRecord(kind="vectors", label=label or "csv", samples=samples)


def parse_bytes(data: bytes, *, filename: str = "upload", label: str | None = None) -> SensorRecord:
    """Dispatch on filename extension / content sniff."""
    name = (filename or "upload").lower()
    text = data.decode("utf-8-sig", errors="replace")
    lbl = label or name.rsplit("/", 1)[-1]
    if name.endswith(".json") or text.lstrip().startswith(("{", "[")):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            if name.endswith(".json"):
                raise ValueError(f"invalid JSON: {exc}") from exc
            return parse_csv_text(text, label=lbl)
        return parse_json_obj(obj, label=lbl)
    return parse_csv_text(text, label=lbl)
