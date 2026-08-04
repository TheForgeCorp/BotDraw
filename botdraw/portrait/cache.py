"""PortraitVector ingest cache (disk + memory) for restyle-without-retrace."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from botdraw.core.jobs import artifact_dir
from botdraw.portrait.models import ColorCluster, CropRect, PortraitVector, RegionPoly

_MEM: dict[str, tuple[float, PortraitVector]] = {}
_MEM_TTL_S = 1800.0


def _crop_key(crop: CropRect | dict | None) -> str:
    if crop is None:
        return "auto"
    if isinstance(crop, dict):
        crop = CropRect.model_validate(crop)
    return f"{crop.source}:{crop.x:.4f}:{crop.y:.4f}:{crop.w:.4f}:{crop.h:.4f}"


def make_ingest_key(
    *,
    image_path: str | Path | None,
    image_bytes: bytes | None = None,
    mode: str,
    quality: str,
    crop: CropRect | dict | None,
    paper: str,
    posterize_levels: int | None = None,
    filter_speckle: int | None = None,
    min_path_points: int | None = None,
    contrast: float | None = None,
    contour_simplify: int | None = None,
    hatch_size: int | None = None,
    linedraw_jitter: float | None = None,
    ensemble: bool | None = None,
    scan_mode: str | None = None,
) -> str:
    h = hashlib.sha256()
    if image_bytes:
        h.update(image_bytes)
    elif image_path and Path(image_path).exists():
        h.update(Path(image_path).read_bytes())
    else:
        h.update(b"synthetic")
    knobs = (
        f"|{mode}|{quality}|{paper}|{_crop_key(crop)}"
        f"|p{posterize_levels}|s{filter_speckle}|m{min_path_points}|c{contrast}"
        f"|cs{contour_simplify}|hs{hatch_size}|lj{linedraw_jitter}|e{ensemble}"
        f"|sm{scan_mode}|mesh2"  # mesh IR + walks + focus-aware bg suppression
    )
    h.update(knobs.encode())
    return h.hexdigest()[:24]


def save_portrait_vector(pv: PortraitVector, ingest_id: str | None = None) -> str:
    iid = ingest_id or pv.ingest_id or hashlib.sha1(str(time.time()).encode()).hexdigest()[:12]
    pv.ingest_id = iid
    out = artifact_dir(f"ingest-{iid}")
    arrays = pv.arrays()
    save_kw = dict(
        rgb=arrays["rgb"],
        lum=arrays["lum"],
        ink_target=arrays["ink_target"],
        edge_map=arrays["edge_map"],
    )
    if "tone_grid" in arrays:
        save_kw["tone_grid"] = arrays["tone_grid"]
    if "tone_codes" in arrays:
        save_kw["tone_codes"] = arrays["tone_codes"]
    if "mesh_edge" in arrays:
        save_kw["mesh_edge"] = arrays["mesh_edge"]
    np.savez_compressed(out / "arrays.npz", **save_kw)
    meta = {
        "width_px": pv.width_px,
        "height_px": pv.height_px,
        "page_w_mm": pv.page_w_mm,
        "page_h_mm": pv.page_h_mm,
        "edge_polylines_mm": pv.edge_polylines_mm,
        "hatch_polylines_mm": pv.hatch_polylines_mm,
        "tone_cell_mm": float(pv.tone_cell_mm or 0.0),
        "tone_origin_mm": list(pv.tone_origin_mm or (0.0, 0.0)),
        "regions": [r.model_dump() for r in pv.regions],
        "clusters": [c.model_dump() for c in pv.clusters],
        "pen_map": pv.pen_map,
        "crop": pv.crop.model_dump(),
        "image_mode": pv.image_mode,
        "quality": pv.quality,
        "ingest_id": iid,
        "meta": pv.meta,
    }
    (out / "vector.json").write_text(json.dumps(meta), encoding="utf-8")
    _MEM[iid] = (time.time(), pv)
    return iid


def load_portrait_vector(ingest_id: str) -> PortraitVector | None:
    now = time.time()
    hit = _MEM.get(ingest_id)
    if hit and now - hit[0] < _MEM_TTL_S:
        return hit[1]
    out = artifact_dir(f"ingest-{ingest_id}")
    meta_path = out / "vector.json"
    arr_path = out / "arrays.npz"
    if not meta_path.exists() or not arr_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    data = np.load(arr_path)
    origin = meta.get("tone_origin_mm") or [0.0, 0.0]
    pv = PortraitVector(
        width_px=meta["width_px"],
        height_px=meta["height_px"],
        page_w_mm=meta["page_w_mm"],
        page_h_mm=meta["page_h_mm"],
        rgb=data["rgb"],
        lum=data["lum"],
        ink_target=data["ink_target"],
        edge_map=data["edge_map"],
        edge_polylines_mm=meta.get("edge_polylines_mm") or [],
        hatch_polylines_mm=meta.get("hatch_polylines_mm") or [],
        tone_grid=data["tone_grid"] if "tone_grid" in data.files else None,
        tone_codes=data["tone_codes"] if "tone_codes" in data.files else None,
        mesh_edge=data["mesh_edge"] if "mesh_edge" in data.files else None,
        tone_cell_mm=float(meta.get("tone_cell_mm") or 0.0),
        tone_origin_mm=(float(origin[0]), float(origin[1])),
        regions=[RegionPoly.model_validate(r) for r in meta.get("regions") or []],
        clusters=[ColorCluster.model_validate(c) for c in meta.get("clusters") or []],
        pen_map=meta.get("pen_map") or {},
        crop=CropRect.model_validate(meta.get("crop") or {}),
        image_mode=meta.get("image_mode") or "photo",
        quality=meta.get("quality") or "booth-balanced",
        ingest_id=ingest_id,
        meta=meta.get("meta") or {},
    )
    _MEM[ingest_id] = (now, pv)
    return pv


def cache_get_by_key(key: str) -> PortraitVector | None:
    """Optional key→id index stored beside artifacts."""
    idx = Path("jobs") / "ingest_index"
    idx.mkdir(parents=True, exist_ok=True)
    path = idx / f"{key}.txt"
    if not path.exists():
        return None
    return load_portrait_vector(path.read_text(encoding="utf-8").strip())


def cache_put_key(key: str, ingest_id: str) -> None:
    idx = Path("jobs") / "ingest_index"
    idx.mkdir(parents=True, exist_ok=True)
    (idx / f"{key}.txt").write_text(ingest_id, encoding="utf-8")


def resolve_portrait_vector(
    *,
    image_path: str | Path | None,
    mode: str,
    quality: str,
    paper: str,
    crop: Any = None,
    reuse_ingest: bool = False,
    ingest_id: str | None = None,
    force_reingest: bool = False,
    auto_frame: bool = True,
    image_bytes: bytes | None = None,
    posterize_levels: int | None = None,
    filter_speckle: int | None = None,
    min_path_points: int | None = None,
    contrast: float | None = None,
    contour_simplify: int | None = None,
    hatch_size: int | None = None,
    linedraw_jitter: float | None = None,
    ensemble: bool | None = None,
    scan_mode: str | None = None,
) -> tuple[PortraitVector, bool]:
    """Return (vector, cache_hit)."""
    from botdraw.portrait.ingest import ingest_portrait

    contrast_v = 1.12 if contrast is None else float(contrast)
    key_kwargs = dict(
        posterize_levels=posterize_levels,
        filter_speckle=filter_speckle,
        min_path_points=min_path_points,
        contrast=contrast_v,
        contour_simplify=contour_simplify,
        hatch_size=hatch_size,
        linedraw_jitter=linedraw_jitter,
        ensemble=ensemble,
        scan_mode=scan_mode,
    )

    if not force_reingest:
        if reuse_ingest and ingest_id:
            pv = load_portrait_vector(ingest_id)
            if pv is not None:
                return pv, True
        key = make_ingest_key(
            image_path=image_path,
            image_bytes=image_bytes,
            mode=mode,
            quality=quality,
            crop=crop,
            paper=paper,
            **key_kwargs,
        )
        pv = cache_get_by_key(key)
        if pv is not None:
            return pv, True

    pv = ingest_portrait(
        image_path,
        mode=mode,
        quality=quality,
        paper=paper,
        crop=crop,
        auto_frame=auto_frame if crop is None else False,
        **key_kwargs,
    )
    iid = save_portrait_vector(pv)
    key = make_ingest_key(
        image_path=image_path,
        image_bytes=image_bytes,
        mode=mode,
        quality=quality,
        crop=crop or pv.crop,
        paper=paper,
        **key_kwargs,
    )
    cache_put_key(key, iid)
    return pv, False
