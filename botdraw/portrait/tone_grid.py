"""Tone grid API — backed by shared portrait mesh (interface walks).

Kept as the stable import surface for cache/UI/restyle. Detection + stroke
emission live in portrait_mesh.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from botdraw.portrait.portrait_mesh import build_portrait_mesh, strokes_from_mesh_walks


def build_tone_grid(
    lum: np.ndarray,
    ink_target: np.ndarray,
    *,
    cell_px: int,
    edge_map: np.ndarray | None = None,
    page_w_mm: float,
    page_h_mm: float,
    max_code: int = 4,
) -> dict[str, Any]:
    """Build tone_grid / tone_codes (mesh IR subset)."""
    return build_portrait_mesh(
        lum,
        ink_target,
        cell_px=cell_px,
        edge_map=edge_map,
        page_w_mm=page_w_mm,
        page_h_mm=page_h_mm,
        max_code=max_code,
    )


def strokes_from_tone_grid(
    tone_codes: np.ndarray,
    *,
    cell_px: float,
    img_w: int,
    img_h: int,
    page_w: float,
    page_h: float,
    style: str = "hatch",
    jitter: float = 0.04,
    seed: int = 1,
    max_paths: int = 4000,
    mesh: dict[str, Any] | None = None,
    face: np.ndarray | None = None,
) -> list[list[tuple[float, float]]]:
    """Emit shade strokes via mesh interface walks (rebuilds links if needed)."""
    if mesh is None:
        codes = np.asarray(tone_codes, dtype=np.uint8)
        # Reconstruct H links from codes alone (restyle / cache without full mesh)
        c = codes.astype(np.int16)
        in_band = (c >= 1) & (c <= 4)
        link_h = in_band[:, :-1] & in_band[:, 1:] & (np.abs(c[:, :-1] - c[:, 1:]) <= 1)
        mesh_face = None
        if face is not None:
            f = np.asarray(face)
            if f.shape != codes.shape:
                from PIL import Image

                f = (
                    np.asarray(
                        Image.fromarray((f > 0).astype(np.uint8) * 255, mode="L").resize(
                            (codes.shape[1], codes.shape[0]), Image.Resampling.NEAREST
                        ),
                        dtype=np.uint8,
                    )
                    > 127
                )
            mesh_face = f.astype(np.uint8)
        mesh = {
            "tone_codes": codes,
            "tone_cell_px": float(cell_px),
            "link_h": link_h,
            "mesh_face": mesh_face,
            "img_shape": (img_h, img_w),
        }
    return strokes_from_mesh_walks(
        mesh,
        img_w=img_w,
        img_h=img_h,
        page_w=page_w,
        page_h=page_h,
        style=style,
        jitter=jitter,
        seed=seed,
        max_paths=max_paths,
    )


def tone_codes_heatmap_rgb(tone_codes: np.ndarray) -> np.ndarray:
    """False-color preview: 0=paper, 1–4=yellow→red, 5=teal (edge-only)."""
    h, w = tone_codes.shape
    out = np.full((h, w, 3), 247, dtype=np.uint8)
    palette = {
        1: (250, 220, 120),
        2: (240, 170, 70),
        3: (220, 100, 50),
        4: (160, 40, 60),
        5: (40, 160, 180),
    }
    for code, rgb in palette.items():
        out[tone_codes == code] = rgb
    return out
