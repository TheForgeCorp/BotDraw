"""PortraitBot Phase B classic gold-set harness.

Gate-1 defaults: classic line_source, hatch off, AI off, ensemble off.
People + objects fixtures under tests/fixtures/portrait/gold/.
"""

from __future__ import annotations

import base64
import html
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from botdraw.core.models import QUALITY_LIMITS, QualityPreset
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.preview import portrait_vector_raw_svg

Category = Literal["people", "objects"]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_DIR = REPO_ROOT / "tests" / "fixtures" / "portrait" / "gold"
IDENTITY_TARGET_EDGES = 200  # aspirational for real photos; synthetic floors are lower


@dataclass(frozen=True)
class GoldCase:
    id: str
    category: Category
    file: str
    label: str
    min_edges: int
    notes: str = ""


@dataclass
class GateCheck:
    key: str
    label: str
    passed: bool
    detail: str


@dataclass
class GoldResult:
    case: GoldCase
    passed: bool
    checks: list[GateCheck]
    edge_count: int
    hatch_count: int
    path_budget: int
    line_source: str
    scan_mode: str
    quality: str
    timing_s: dict[str, Any]
    crop: dict[str, Any]
    page_mm: tuple[float, float]
    source_png_b64: str
    raw_svg: str
    wall_s: float
    identity_target_met: bool


DEFAULT_MANIFEST: list[dict[str, Any]] = [
    {
        "id": "person-front",
        "category": "people",
        "file": "people/person-front.png",
        "label": "Person · front",
        "min_edges": 40,
        "notes": "Synthetic face + shoulders for structure identity",
    },
    {
        "id": "person-profile",
        "category": "people",
        "file": "people/person-profile.png",
        "label": "Person · profile",
        "min_edges": 35,
        "notes": "Side silhouette + features",
    },
    {
        "id": "person-groupish",
        "category": "people",
        "file": "people/person-groupish.png",
        "label": "Person · busy collar",
        "min_edges": 40,
        "notes": "Hair strands + garment folds stress travel/noise",
    },
    {
        "id": "object-mug",
        "category": "objects",
        "file": "objects/mug.png",
        "label": "Object · mug",
        "min_edges": 12,
        "notes": "Cylinder + handle silhouette",
    },
    {
        "id": "object-camera",
        "category": "objects",
        "file": "objects/camera.png",
        "label": "Object · camera",
        "min_edges": 18,
        "notes": "Nested ellipses / body",
    },
    {
        "id": "object-chair",
        "category": "objects",
        "file": "objects/chair.png",
        "label": "Object · chair",
        "min_edges": 15,
        "notes": "Straight structure lines / legs",
    },
]


def _noise(img: Image.Image, amp: float = 6.0, seed: int = 0) -> Image.Image:
    arr = np.asarray(img, dtype=np.float32)
    arr += np.random.default_rng(seed).normal(0.0, amp, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _render_person_front(size: int = 640) -> Image.Image:
    img = Image.new("RGB", (size, size), (210, 205, 198))
    d = ImageDraw.Draw(img)
    for i in range(8):
        pad = i * 20
        d.ellipse([pad, pad, size - pad, size - pad], outline=(200 - i * 5, 198 - i * 4, 190 - i * 3))
    d.ellipse([size * 0.18, size * 0.05, size * 0.82, size * 0.58], fill=(35, 28, 22))
    d.ellipse([size * 0.25, size * 0.16, size * 0.75, size * 0.74], fill=(205, 160, 135))
    d.ellipse([size * 0.30, size * 0.48, size * 0.42, size * 0.62], fill=(185, 140, 120))
    d.ellipse([size * 0.58, size * 0.48, size * 0.70, size * 0.62], fill=(185, 140, 120))
    d.arc([size * 0.33, size * 0.33, size * 0.45, size * 0.42], 200, 340, fill=(45, 30, 25), width=4)
    d.arc([size * 0.55, size * 0.33, size * 0.67, size * 0.42], 200, 340, fill=(45, 30, 25), width=4)
    d.ellipse([size * 0.35, size * 0.38, size * 0.45, size * 0.46], fill=(245, 245, 245))
    d.ellipse([size * 0.55, size * 0.38, size * 0.65, size * 0.46], fill=(245, 245, 245))
    d.ellipse([size * 0.38, size * 0.40, size * 0.43, size * 0.45], fill=(25, 35, 50))
    d.ellipse([size * 0.58, size * 0.40, size * 0.63, size * 0.45], fill=(25, 35, 50))
    d.polygon(
        [(size * 0.5, size * 0.44), (size * 0.46, size * 0.56), (size * 0.54, size * 0.56)],
        fill=(190, 140, 120),
    )
    d.arc([size * 0.38, size * 0.54, size * 0.62, size * 0.68], 10, 170, fill=(130, 55, 65), width=4)
    d.ellipse([size * 0.22, size * 0.38, size * 0.29, size * 0.52], fill=(195, 145, 125))
    d.ellipse([size * 0.71, size * 0.38, size * 0.78, size * 0.52], fill=(195, 145, 125))
    for i in range(12):
        x0 = size * (0.25 + i * 0.04)
        d.line([(x0, size * 0.12), (x0 + 8, size * 0.40)], fill=(20, 15, 12), width=2)
    d.rectangle([size * 0.40, size * 0.70, size * 0.60, size * 0.86], fill=(205, 160, 135))
    d.polygon(
        [
            (size * 0.10, size * 0.98),
            (size * 0.90, size * 0.98),
            (size * 0.78, size * 0.78),
            (size * 0.22, size * 0.78),
        ],
        fill=(45, 65, 85),
    )
    d.line(
        [(size * 0.40, size * 0.78), (size * 0.50, size * 0.86), (size * 0.60, size * 0.78)],
        fill=(30, 45, 60),
        width=3,
    )
    return _noise(img, 6, seed=1).filter(ImageFilter.GaussianBlur(0.6))


def _render_person_profile(size: int = 640) -> Image.Image:
    img = Image.new("RGB", (size, size), (222, 218, 210))
    d = ImageDraw.Draw(img)
    d.ellipse([size * 0.10, size * 0.08, size * 0.70, size * 0.62], fill=(30, 24, 20))
    d.polygon(
        [
            (size * 0.28, size * 0.22),
            (size * 0.55, size * 0.18),
            (size * 0.72, size * 0.32),
            (size * 0.68, size * 0.48),
            (size * 0.58, size * 0.58),
            (size * 0.40, size * 0.62),
            (size * 0.28, size * 0.50),
        ],
        fill=(205, 160, 135),
    )
    d.ellipse([size * 0.48, size * 0.34, size * 0.56, size * 0.42], fill=(245, 245, 245))
    d.ellipse([size * 0.51, size * 0.36, size * 0.55, size * 0.40], fill=(25, 35, 50))
    d.polygon(
        [(size * 0.68, size * 0.38), (size * 0.78, size * 0.42), (size * 0.68, size * 0.46)],
        fill=(190, 145, 125),
    )
    d.arc([size * 0.52, size * 0.48, size * 0.66, size * 0.58], 20, 160, fill=(130, 55, 65), width=3)
    d.ellipse([size * 0.30, size * 0.36, size * 0.38, size * 0.50], fill=(195, 145, 125))
    d.rectangle([size * 0.32, size * 0.60, size * 0.48, size * 0.82], fill=(205, 160, 135))
    d.polygon(
        [
            (size * 0.10, size * 0.98),
            (size * 0.70, size * 0.98),
            (size * 0.55, size * 0.78),
            (size * 0.22, size * 0.78),
        ],
        fill=(70, 55, 45),
    )
    for i in range(10):
        y = size * (0.12 + i * 0.04)
        d.line([(size * 0.12, y), (size * 0.40, y + 10)], fill=(18, 12, 10), width=2)
    return _noise(img, 5, seed=2).filter(ImageFilter.GaussianBlur(0.5))


def _render_person_groupish(size: int = 640) -> Image.Image:
    img = _render_person_front(size)
    d = ImageDraw.Draw(img)
    # denser garment folds + necklace
    for i in range(8):
        y = size * (0.80 + i * 0.015)
        d.arc([size * 0.22, y - 20, size * 0.78, y + 40], 200, 340, fill=(25, 40, 55), width=2)
    for i in range(6):
        x = size * (0.42 + i * 0.03)
        d.ellipse([x, size * 0.84, x + 10, size * 0.90], outline=(180, 160, 80), width=2)
    return _noise(img, 7, seed=3)


def _render_mug(size: int = 640) -> Image.Image:
    img = Image.new("RGB", (size, size), (248, 246, 240))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [size * 0.28, size * 0.28, size * 0.68, size * 0.82],
        radius=22,
        fill=(210, 85, 70),
        outline=(35, 35, 35),
        width=4,
    )
    d.ellipse([size * 0.28, size * 0.20, size * 0.68, size * 0.36], outline=(35, 35, 35), width=4)
    d.ellipse([size * 0.34, size * 0.24, size * 0.62, size * 0.32], fill=(200, 200, 195))
    d.arc([size * 0.62, size * 0.40, size * 0.88, size * 0.70], -90, 90, fill=(35, 35, 35), width=10)
    d.rectangle([size * 0.28, size * 0.50, size * 0.68, size * 0.58], fill=(255, 255, 255))
    d.line([(size * 0.32, size * 0.72), (size * 0.64, size * 0.72)], fill=(35, 35, 35), width=2)
    return _noise(img, 4, seed=4)


def _render_camera(size: int = 640) -> Image.Image:
    img = Image.new("RGB", (size, size), (230, 232, 236))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [size * 0.16, size * 0.32, size * 0.84, size * 0.74],
        radius=22,
        fill=(35, 35, 38),
        outline=(10, 10, 12),
        width=3,
    )
    d.ellipse([size * 0.32, size * 0.36, size * 0.68, size * 0.70], fill=(20, 20, 22), outline=(180, 180, 185), width=4)
    d.ellipse([size * 0.40, size * 0.42, size * 0.60, size * 0.62], fill=(60, 90, 120), outline=(220, 220, 225), width=2)
    d.ellipse([size * 0.46, size * 0.48, size * 0.54, size * 0.56], fill=(15, 15, 18))
    d.rectangle([size * 0.20, size * 0.24, size * 0.42, size * 0.34], fill=(50, 50, 55), outline=(10, 10, 12), width=2)
    d.rectangle([size * 0.70, size * 0.38, size * 0.80, size * 0.48], fill=(200, 160, 40))
    d.rectangle([size * 0.20, size * 0.55, size * 0.30, size * 0.64], fill=(80, 80, 85))
    d.line([(size * 0.18, size * 0.50), (size * 0.82, size * 0.50)], fill=(90, 90, 95), width=1)
    return _noise(img, 5, seed=5)


def _render_chair(size: int = 640) -> Image.Image:
    img = Image.new("RGB", (size, size), (250, 248, 242))
    d = ImageDraw.Draw(img)
    d.rectangle([size * 0.26, size * 0.16, size * 0.74, size * 0.48], outline=(50, 40, 30), width=7)
    for i in range(5):
        xx = size * 0.32 + i * size * 0.08
        d.line([(xx, size * 0.18), (xx, size * 0.46)], fill=(50, 40, 30), width=3)
    d.rectangle(
        [size * 0.24, size * 0.48, size * 0.76, size * 0.58],
        fill=(140, 100, 70),
        outline=(50, 40, 30),
        width=3,
    )
    for x in (0.28, 0.68):
        d.line([(size * x, size * 0.58), (size * x, size * 0.90)], fill=(50, 40, 30), width=7)
        d.line(
            [(size * (x + 0.05), size * 0.58), (size * (x + 0.05), size * 0.90)],
            fill=(50, 40, 30),
            width=4,
        )
    d.line([(size * 0.28, size * 0.72), (size * 0.73, size * 0.72)], fill=(50, 40, 30), width=4)
    return _noise(img, 4, seed=6)


FIXTURE_RENDERERS: dict[str, Any] = {
    "people/person-front.png": _render_person_front,
    "people/person-profile.png": _render_person_profile,
    "people/person-groupish.png": _render_person_groupish,
    "objects/mug.png": _render_mug,
    "objects/camera.png": _render_camera,
    "objects/chair.png": _render_chair,
}


def gold_dir(root: Path | None = None) -> Path:
    return Path(root) if root else DEFAULT_GOLD_DIR


def manifest_path(root: Path | None = None) -> Path:
    return gold_dir(root) / "manifest.json"


def load_manifest(root: Path | None = None) -> list[GoldCase]:
    path = manifest_path(root)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = data.get("cases", data) if isinstance(data, dict) else data
    else:
        cases = DEFAULT_MANIFEST
    out: list[GoldCase] = []
    for row in cases:
        out.append(
            GoldCase(
                id=str(row["id"]),
                category=row["category"],  # type: ignore[arg-type]
                file=str(row["file"]),
                label=str(row.get("label") or row["id"]),
                min_edges=int(row.get("min_edges") or 10),
                notes=str(row.get("notes") or ""),
            )
        )
    return out


def ensure_gold_fixtures(*, root: Path | None = None, force: bool = False) -> Path:
    """Write synthetic PNG fixtures + manifest (idempotent)."""
    base = gold_dir(root)
    (base / "people").mkdir(parents=True, exist_ok=True)
    (base / "objects").mkdir(parents=True, exist_ok=True)
    for rel, renderer in FIXTURE_RENDERERS.items():
        dest = base / rel
        if force or not dest.exists():
            renderer().save(dest, format="PNG", optimize=True)
    man = {
        "version": 1,
        "description": (
            "Phase B classic gold set — synthetic people + objects. "
            "Replace with licensed/demo photos when available; keep ids stable."
        ),
        "gate": {
            "line_source": "classic",
            "hatch": "off",
            "ai_review": "off",
            "ensemble": False,
            "scan_mode": "edges",
            "identity_target_edges": IDENTITY_TARGET_EDGES,
        },
        "cases": DEFAULT_MANIFEST,
    }
    manifest_path(root).write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return base


def _png_b64(path: Path, max_side: int = 320) -> str:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def assess_gate(
    *,
    case: GoldCase,
    edge_count: int,
    hatch_count: int,
    line_source: str,
    path_budget: int,
    crop: dict[str, Any],
    raw_svg: str,
) -> list[GateCheck]:
    classic_ok = line_source in {"classic", "auto"}
    identity_ok = edge_count >= case.min_edges
    budget_ok = (edge_count + hatch_count) <= path_budget
    hatch_ok = hatch_count == 0
    crop_w = float(crop.get("w") or 0)
    crop_h = float(crop.get("h") or 0)
    crop_ok = 0.15 <= crop_w <= 1.0 and 0.15 <= crop_h <= 1.0
    svg_ok = "layer-edges" in raw_svg and raw_svg.count("<path") >= 1
    # Noise/travel proxy: enough ink for structure, not a single scribble explosion
    travel_ok = edge_count <= path_budget and edge_count >= max(3, case.min_edges // 4)

    return [
        GateCheck("identity", "Identity (structure alone)", identity_ok, f"{edge_count} ≥ {case.min_edges} edges"),
        GateCheck("noise", "Noise / travel OK", travel_ok, f"{edge_count} paths within budget band"),
        GateCheck("budget", "Path budget OK", budget_ok, f"{edge_count + hatch_count} / {path_budget}"),
        GateCheck("crop", "Crop OK", crop_ok, f"w={crop_w:.2f} h={crop_h:.2f}"),
        GateCheck("classic", "Classic-only pass", classic_ok and hatch_ok and svg_ok, f"line_source={line_source}, hatch={hatch_count}, svg={'ok' if svg_ok else 'bad'}"),
    ]


def run_gold_case(
    case: GoldCase,
    *,
    root: Path | None = None,
    quality: str | QualityPreset = QualityPreset.BOOTH_BALANCED,
    paper: str = "A5",
    scan_mode: str = "edges",
) -> GoldResult:
    base = gold_dir(root)
    path = base / case.file
    if not path.exists():
        ensure_gold_fixtures(root=root)
    quality_enum = quality if isinstance(quality, QualityPreset) else QualityPreset(quality)
    budget = int(QUALITY_LIMITS[quality_enum]["max_paths"])
    t0 = time.perf_counter()
    pv = ingest_portrait(
        image_path=path,
        mode="photo",
        quality=quality_enum,
        paper=paper,
        auto_frame=True,
        hatch_size=0,
        line_source="classic",
        scan_mode=scan_mode,
        ensemble=False,
    )
    wall = time.perf_counter() - t0
    edge_count = len(pv.edge_polylines_mm)
    hatch_count = len(pv.hatch_polylines_mm)
    line_source = str((pv.meta or {}).get("line_source") or "classic")
    raw_svg = portrait_vector_raw_svg(pv)
    crop = pv.crop.model_dump() if hasattr(pv.crop, "model_dump") else dict(pv.crop)
    checks = assess_gate(
        case=case,
        edge_count=edge_count,
        hatch_count=hatch_count,
        line_source=line_source,
        path_budget=budget,
        crop=crop,
        raw_svg=raw_svg,
    )
    return GoldResult(
        case=case,
        passed=all(c.passed for c in checks),
        checks=checks,
        edge_count=edge_count,
        hatch_count=hatch_count,
        path_budget=budget,
        line_source=line_source,
        scan_mode=str((pv.meta or {}).get("scan_mode") or scan_mode),
        quality=quality_enum.value,
        timing_s=dict((pv.meta or {}).get("timing_s") or {}),
        crop=crop,
        page_mm=(float(pv.page_w_mm), float(pv.page_h_mm)),
        source_png_b64=_png_b64(path),
        raw_svg=raw_svg,
        wall_s=wall,
        identity_target_met=edge_count >= IDENTITY_TARGET_EDGES,
    )


def run_gold_set(
    *,
    root: Path | None = None,
    quality: str | QualityPreset = QualityPreset.BOOTH_BALANCED,
    paper: str = "A5",
    scan_mode: str = "edges",
) -> list[GoldResult]:
    ensure_gold_fixtures(root=root)
    return [
        run_gold_case(case, root=root, quality=quality, paper=paper, scan_mode=scan_mode)
        for case in load_manifest(root)
    ]


def _badge(ok: bool, label: str | None = None) -> str:
    text = label or ("pass" if ok else "fail")
    cls = "pass" if ok else "fail"
    return f'<span class="badge {cls}">{html.escape(text)}</span>'


def render_gold_report_html(
    results: list[GoldResult],
    *,
    title: str = "PortraitBot Phase B — Classic gold gate",
    vision_html: str = "",
) -> str:
    passed_n = sum(1 for r in results if r.passed)
    total = len(results)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    cards = []
    for r in results:
        checks_html = "".join(
            f'<li class="{"ok" if c.passed else "bad"}"><strong>{html.escape(c.label)}</strong> '
            f"{_badge(c.passed)} <span class='det'>{html.escape(c.detail)}</span></li>"
            for c in r.checks
        )
        target = _badge(r.identity_target_met, "studio ≥200" if r.identity_target_met else "studio target later")
        cards.append(
            f"""
<article class="card {'is-pass' if r.passed else 'is-fail'}" id="{html.escape(r.case.id)}">
  <header>
    <div>
      <p class="cat">{html.escape(r.case.category)}</p>
      <h2>{html.escape(r.case.label)}</h2>
      <p class="notes">{html.escape(r.case.notes)}</p>
    </div>
    {_badge(r.passed, "GATE PASS" if r.passed else "GATE FAIL")}
  </header>
  <div class="grid">
    <figure>
      <figcaption>Source</figcaption>
      <img src="data:image/png;base64,{r.source_png_b64}" alt="{html.escape(r.case.label)} source"/>
    </figure>
    <figure class="svg-fig">
      <figcaption>Raw SVG · structure (hatch off)</figcaption>
      <div class="svg-wrap">{r.raw_svg}</div>
    </figure>
  </div>
  <div class="meta">
    <div><span>edges</span><strong>{r.edge_count}</strong></div>
    <div><span>hatch</span><strong>{r.hatch_count}</strong></div>
    <div><span>budget</span><strong>{r.edge_count + r.hatch_count}/{r.path_budget}</strong></div>
    <div><span>line_source</span><strong>{html.escape(r.line_source)}</strong></div>
    <div><span>scan</span><strong>{html.escape(r.scan_mode)}</strong></div>
    <div><span>quality</span><strong>{html.escape(r.quality)}</strong></div>
    <div><span>wall</span><strong>{r.wall_s:.2f}s</strong></div>
    <div><span>identity target</span>{target}</div>
  </div>
  <ul class="checks">{checks_html}</ul>
</article>
"""
        )

    vision_block = ""
    if vision_html:
        vision_block = f"""
<section class="vision" id="vision-loop">
  <h2>Studio vision loop (manual fixtures)</h2>
  <p class="lede">
    Gold gate stays AI-off. This section proves the 3-turn studio path
    (scene → structure → confirm) under committed subscription JSON — no API key.
  </p>
  {vision_html}
</section>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  :root {{
    --ink: #1d1d1f;
    --muted: #6e6e73;
    --faint: #8e8e93;
    --line: #d2d2d7;
    --panel: #ffffff;
    --soft: #f5f5f7;
    --bg: #ececef;
    --teal: #0e7490;
    --ok: #1f7a3f;
    --bad: #b42318;
    --warn: #a15c00;
    --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: var(--font);
    color: var(--ink);
    background:
      radial-gradient(900px 420px at 12% -10%, #ffffff 0%, transparent 55%),
      linear-gradient(180deg, #f7f7f8 0%, var(--bg) 40%, #e8e8eb 100%);
    line-height: 1.45;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
  header.hero {{
    display: grid;
    gap: 0.75rem;
    margin-bottom: 1.75rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid var(--line);
  }}
  .eyebrow {{
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--faint);
    font-weight: 600;
  }}
  h1 {{ margin: 0; font-size: clamp(1.6rem, 3vw, 2.1rem); letter-spacing: -0.03em; }}
  .lede {{ margin: 0; max-width: 62ch; color: var(--muted); }}
  .summary {{
    display: flex; flex-wrap: wrap; gap: 0.5rem 0.75rem; align-items: center;
    font-family: var(--mono); font-size: 0.8rem;
  }}
  .badge {{
    display: inline-flex; align-items: center; gap: 0.25rem;
    padding: 0.15rem 0.45rem; border-radius: 4px;
    font-family: var(--mono); font-size: 0.7rem; font-weight: 600;
  }}
  .badge.pass {{ background: #e5f5ea; color: var(--ok); }}
  .badge.fail {{ background: #fdecea; color: var(--bad); }}
  .toc {{
    display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0 0 1.5rem;
  }}
  .toc a {{
    text-decoration: none; color: var(--ink); border: 1px solid var(--line);
    background: var(--panel); padding: 0.3rem 0.55rem; border-radius: 6px; font-size: 0.8rem;
  }}
  .card {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 1rem; margin: 0 0 1rem;
  }}
  .card header {{ display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }}
  .cat {{ margin: 0; font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--faint); }}
  .card h2 {{ margin: 0.15rem 0 0; font-size: 1.15rem; }}
  .notes {{ margin: 0.25rem 0 0; color: var(--muted); font-size: 0.9rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.65rem; margin-top: 0.75rem; }}
  figure {{ margin: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--soft); }}
  figcaption {{ padding: 0.35rem 0.5rem; font-family: var(--mono); font-size: 0.65rem; color: var(--faint); border-bottom: 1px solid var(--line); }}
  figure img {{ display: block; width: 100%; height: auto; }}
  .svg-fig .svg-wrap {{
    padding: 0.5rem; min-height: 180px;
    display: flex; align-items: center; justify-content: center;
  }}
  .svg-wrap svg {{ width: 100%; height: auto; max-height: 360px; }}
  .meta {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.45rem 0.65rem; margin: 0.85rem 0 0.55rem;
    font-family: var(--mono); font-size: 0.72rem;
  }}
  @media (max-width: 760px) {{ .meta {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  .meta span {{ display: block; color: var(--faint); }}
  .meta strong {{ color: var(--ink); font-weight: 600; }}
  .checks {{ list-style: none; margin: 0.4rem 0 0; padding: 0; display: grid; gap: 0.3rem; }}
  .checks li {{
    display: flex; flex-wrap: wrap; gap: 0.35rem 0.55rem; align-items: center;
    padding: 0.4rem 0.5rem; border-radius: 6px; background: var(--soft);
    font-size: 0.85rem;
  }}
  .checks li.bad {{ background: #fff5f4; }}
  .checks .det {{ color: var(--muted); font-family: var(--mono); font-size: 0.75rem; }}
  .vision {{
    margin: 2rem 0 1rem; padding: 1.25rem 0 0; border-top: 1px solid var(--line);
  }}
  .vision h2 {{ margin: 0 0 0.35rem; font-size: 1.25rem; letter-spacing: -0.02em; }}
  .vision-case {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 1rem; margin: 0.85rem 0;
  }}
  .vision-case h3 {{ margin: 0 0 0.5rem; font-size: 1.05rem; }}
  .vision-turns {{
    display: grid; gap: 0.45rem; font-family: var(--mono); font-size: 0.78rem;
  }}
  .vision-turn {{
    display: grid; grid-template-columns: 4.5rem 5.5rem 3.5rem 1fr;
    gap: 0.4rem; align-items: baseline; padding: 0.4rem 0.5rem;
    background: var(--soft); border-radius: 6px;
  }}
  @media (max-width: 640px) {{
    .vision-turn {{ grid-template-columns: 3.5rem 1fr; }}
  }}
  footer.note {{
    margin-top: 1.5rem; color: var(--muted); font-size: 0.85rem; max-width: 70ch;
  }}
  code {{ font-family: var(--mono); font-size: 0.85em; }}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <p class="eyebrow">BotDraw · PortraitBot · Phase B</p>
      <h1>{html.escape(title)}</h1>
      <p class="lede">
        Classic baseline, hatch off, AI off. Judge on structure (Raw SVG).
        Synthetic people + objects until photo gold replaces them. Studio identity
        target ({IDENTITY_TARGET_EDGES} edges) is shown separately from the synthetic floor.
      </p>
      <div class="summary">
        {_badge(passed_n == total and total > 0, f"{passed_n}/{total} passed")}
        <span>generated {html.escape(generated)}</span>
        <span>quality booth-balanced · scan edges · line_source classic</span>
        {"<span>vision fixtures appended</span>" if vision_html else ""}
      </div>
    </header>
    <nav class="toc">
      {''.join(f'<a href="#{html.escape(r.case.id)}">{html.escape(r.case.label)}</a>' for r in results)}
      {"<a href='#vision-loop'>Vision loop</a>" if vision_html else ""}
    </nav>
    {''.join(cards)}
    {vision_block}
    <footer class="note">
      Gate checklist mirrors Dev Lab: identity, noise/travel, path budget, crop, classic-only.
      Tone/hatch is gate-2. Replace fixtures under <code>tests/fixtures/portrait/gold/</code>
      with real photos when available; keep case ids stable for the harness.
      Full pass-by-pass visuals: <code>botdraw vision loop-demo</code>.
    </footer>
  </div>
</body>
</html>
"""


def render_vision_fixtures_section(
    *,
    root: Path | None = None,
    case_ids: tuple[str, ...] = ("objects/mug",),
) -> tuple[str, list[dict[str, Any]]]:
    """
    Run the studio 3-turn loop under manual fixtures for selected gold cases.
    Returns (html_fragment, slim_pass_dicts). Does not change gold gate defaults.
    """
    from botdraw.portrait.vision_loop import (
        DEFAULT_TURNS_DIR,
        ensure_manual_turn_fixtures,
        run_vision_structure_loop,
    )

    ensure_gold_fixtures(root=root)
    turns = ensure_manual_turn_fixtures(root=DEFAULT_TURNS_DIR, force=False)
    base = gold_dir(root)
    blocks: list[str] = []
    slim_all: list[dict[str, Any]] = []
    for cid in case_ids:
        path = base / f"{cid}.png"
        if not path.exists():
            continue
        history = run_vision_structure_loop(
            image_path=path,
            max_turns=3,
            turns_dir=turns,
            case_label=cid,
        )
        rows = []
        for p in history:
            ov = f"{p.overall:.2f}" if p.overall is not None else "—"
            kind = p.kind + (" · re-ingest" if p.reingest else "")
            rows.append(
                f'<div class="vision-turn">'
                f"<span>pass {p.turn}</span>"
                f"<span>{html.escape(kind)}</span>"
                f"<span>{ov}</span>"
                f"<span>{html.escape(p.summary or '')}</span>"
                f"</div>"
            )
            slim_all.append(
                {
                    "case": cid,
                    "turn": p.turn,
                    "kind": p.kind,
                    "overall": p.overall,
                    "summary": p.summary,
                    "edge_count": p.edge_count,
                    "reingest": p.reingest,
                }
            )
        blocks.append(
            f'<article class="vision-case" id="vision-{html.escape(cid.replace("/", "-"))}">'
            f"<h3>{html.escape(cid)}</h3>"
            f'<div class="vision-turns">{"".join(rows)}</div>'
            f"</article>"
        )
    return "\n".join(blocks), slim_all


def write_gold_report(
    out: Path,
    *,
    root: Path | None = None,
    quality: str | QualityPreset = QualityPreset.BOOTH_BALANCED,
    with_vision_fixtures: bool = False,
) -> tuple[Path, list[GoldResult]]:
    results = run_gold_set(root=root, quality=quality)
    vision_html = ""
    vision_slim: list[dict[str, Any]] = []
    if with_vision_fixtures:
        case_ids: list[str] = []
        gdir = gold_dir(root)
        mug = gdir / "objects" / "mug.png"
        if mug.exists():
            case_ids.append("objects/mug")
        people = sorted((gdir / "people").glob("*.png")) if (gdir / "people").is_dir() else []
        if people:
            case_ids.append(f"people/{people[0].stem}")
        if not case_ids and (gdir / "objects").is_dir():
            objs = sorted((gdir / "objects").glob("*.png"))
            if objs:
                case_ids.append(f"objects/{objs[0].stem}")
        vision_html, vision_slim = render_vision_fixtures_section(
            root=root, case_ids=tuple(case_ids) or ("objects/mug",)
        )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_gold_report_html(results, vision_html=vision_html),
        encoding="utf-8",
    )
    if with_vision_fixtures and vision_slim:
        (out.parent / (out.stem + "-vision.json")).write_text(
            json.dumps(vision_slim, indent=2) + "\n",
            encoding="utf-8",
        )
    return out, results
