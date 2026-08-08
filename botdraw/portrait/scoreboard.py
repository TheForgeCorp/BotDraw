"""
Portrait contact sheet: one real photo, every style, side-by-side with
fidelity numbers — extends the ``botdraw/portrait/gold.py`` and
``botdraw/portrait/vision_loop.py`` convention (self-contained committed
HTML + slim JSON sidecar) to real photographs.

This is the human-review layer described in the portrait quality plan:
``fidelity.py`` gives a number that a test can assert on and a PR diff can
show; this gives a picture, because "does this look like the photo" is a
judgment call no metric should be trusted to make alone.
"""
from __future__ import annotations

import base64
import html
import io
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.portrait.fidelity import render_preview_png, score_render
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.neural import neural_available
from botdraw.portrait.pens import assign_pens
from botdraw.portrait.restyle import RESTYLERS, render_from_vector
from botdraw.styles import ensure_styles_loaded, list_styles

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "docs" / "wireframes" / "portraitbot-contact-sheet.html"


@dataclass
class StyleScore:
    style_id: str
    style_name: str
    tone_corr: float
    total_coverage: float
    max_single_pass_coverage: float
    max_single_pass_id: str | None
    pass_count: int
    path_count: int
    wall_s: float
    preview_png_b64: str = field(repr=False)


@dataclass
class ContactSheetResult:
    photo: str
    line_source_requested: str
    line_source_resolved: str
    line_source_warning: str | None
    quality: str
    generated_at: str
    source_png_b64: str = field(repr=False)
    scores: list[StyleScore] = field(default_factory=list)


def _png_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _source_thumb_b64(photo_path: Path, max_side: int = 420) -> str:
    img = Image.open(photo_path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return _png_b64(buf.getvalue())


def _style_names() -> dict[str, str]:
    ensure_styles_loaded()
    return {s["id"]: s["name"] for s in list_styles("portrait")}


def build_contact_sheet(
    photo_path: str | Path,
    *,
    styles: list[str] | None = None,
    quality: QualityPreset = QualityPreset.STUDIO_HQ,
    line_source: str = "auto",
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    seed: int = 42,
) -> ContactSheetResult:
    """Render one photo across every (or a chosen subset of) portrait style,
    scoring each against the fidelity metric and capturing a true-color
    preview — the data behind both the HTML contact sheet and its JSON
    sidecar."""
    photo_path = Path(photo_path)
    palette = load_palette(palette_id)
    pv = ingest_portrait(
        str(photo_path), mode="photo", quality=quality, paper=paper, line_source=line_source
    )
    pv = assign_pens(pv, palette)
    resolved_line_source = str((pv.meta or {}).get("line_source") or "classic")
    line_source_warning = (pv.meta or {}).get("line_source_warning")

    style_ids = styles or list(RESTYLERS.keys())
    names = _style_names()
    params = StyleParams(seed=seed, quality=quality, density=1.0)

    scores: list[StyleScore] = []
    for style_id in style_ids:
        t0 = time.perf_counter()
        layered = render_from_vector(style_id, pv, palette, params)
        wall_s = time.perf_counter() - t0
        report = score_render(layered, palette, pv)
        preview = render_preview_png(layered, palette, max_side=420)
        path_count = sum(len(p.polylines) for p in layered.passes)
        scores.append(
            StyleScore(
                style_id=style_id,
                style_name=names.get(style_id, style_id),
                tone_corr=report.tone_corr,
                total_coverage=report.total_coverage,
                max_single_pass_coverage=report.max_single_pass_coverage,
                max_single_pass_id=report.max_single_pass_id,
                pass_count=len(layered.passes),
                path_count=path_count,
                wall_s=wall_s,
                preview_png_b64=_png_b64(preview),
            )
        )

    return ContactSheetResult(
        photo=str(photo_path),
        line_source_requested=line_source,
        line_source_resolved=resolved_line_source,
        line_source_warning=line_source_warning,
        quality=quality.value if isinstance(quality, QualityPreset) else str(quality),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_png_b64=_source_thumb_b64(photo_path),
        scores=scores,
    )


def _badge(ok: bool, label_ok: str = "OK", label_bad: str = "CHECK") -> str:
    cls = "ok" if ok else "warn"
    return f'<span class="badge {cls}">{label_ok if ok else label_bad}</span>'


def render_contact_sheet_html(result: ContactSheetResult) -> str:
    photo_name = html.escape(Path(result.photo).name)
    warning_html = ""
    if result.line_source_warning:
        warning_html = f'<p class="warning">⚠ {html.escape(result.line_source_warning)}</p>'

    cards = []
    for s in result.scores:
        tone_ok = s.tone_corr > 0.0
        cov_ok = s.max_single_pass_coverage < 0.35
        cards.append(
            f"""
<article class="card">
  <header>
    <h2>{html.escape(s.style_name)}</h2>
    <p class="id">{html.escape(s.style_id)}</p>
  </header>
  <figure><img src="data:image/png;base64,{s.preview_png_b64}" alt="{html.escape(s.style_name)} render"/></figure>
  <div class="meta">
    <div><span>tone_corr</span><strong>{s.tone_corr:+.3f}</strong>{_badge(tone_ok)}</div>
    <div><span>coverage</span><strong>{s.total_coverage:.1%}</strong></div>
    <div><span>max pass</span><strong>{s.max_single_pass_coverage:.1%}</strong>{_badge(cov_ok)}</div>
    <div><span>passes</span><strong>{s.pass_count}</strong></div>
    <div><span>paths</span><strong>{s.path_count}</strong></div>
    <div><span>wall</span><strong>{s.wall_s:.2f}s</strong></div>
  </div>
</article>
"""
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>PortraitBot contact sheet — {photo_name}</title>
<style>
  :root {{
    --ink: #1d1d1f; --muted: #6e6e73; --faint: #8e8e93; --line: #d2d2d7;
    --panel: #ffffff; --soft: #f5f5f7; --bg: #ececef;
    --ok: #1f7a3f; --warn: #a15c00;
    --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: var(--font); color: var(--ink);
    background: linear-gradient(180deg, #f7f7f8 0%, var(--bg) 40%, #e8e8eb 100%);
    line-height: 1.45;
  }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
  header.hero {{ display: flex; gap: 1.5rem; align-items: flex-start; margin-bottom: 1.75rem; padding-bottom: 1.25rem; border-bottom: 1px solid var(--line); }}
  header.hero figure {{ margin: 0; flex: none; width: 160px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
  header.hero img {{ display: block; width: 100%; height: auto; }}
  .eyebrow {{ margin: 0; font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); font-weight: 600; }}
  h1 {{ margin: 0.15rem 0 0.5rem; font-size: clamp(1.4rem, 3vw, 1.9rem); letter-spacing: -0.03em; }}
  .lede {{ margin: 0; color: var(--muted); font-family: var(--mono); font-size: 0.8rem; }}
  .warning {{ margin: 0.5rem 0 0; color: var(--warn); font-family: var(--mono); font-size: 0.8rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 0.85rem; }}
  .card header {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; }}
  .card h2 {{ margin: 0; font-size: 1rem; }}
  .card .id {{ margin: 0; font-family: var(--mono); font-size: 0.68rem; color: var(--faint); }}
  .card figure {{ margin: 0.6rem 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--soft); }}
  .card img {{ display: block; width: 100%; height: auto; }}
  .meta {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.35rem 0.6rem; font-family: var(--mono); font-size: 0.72rem; }}
  .meta div {{ display: flex; align-items: center; gap: 0.35rem; }}
  .meta span {{ color: var(--faint); }}
  .meta strong {{ color: var(--ink); font-weight: 600; }}
  .badge {{ padding: 0.05rem 0.35rem; border-radius: 4px; font-size: 0.62rem; font-weight: 700; }}
  .badge.ok {{ background: #e5f5ea; color: var(--ok); }}
  .badge.warn {{ background: #fdf1de; color: var(--warn); }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <figure><img src="data:image/png;base64,{result.source_png_b64}" alt="source"/></figure>
    <div>
      <p class="eyebrow">PortraitBot contact sheet</p>
      <h1>{photo_name}</h1>
      <p class="lede">line_source={html.escape(result.line_source_resolved)} (requested {html.escape(result.line_source_requested)}) · quality={html.escape(result.quality)} · generated {html.escape(result.generated_at)}</p>
      {warning_html}
    </div>
  </header>
  <div class="grid">
    {''.join(cards)}
  </div>
</div>
</body>
</html>
"""


def write_contact_sheet(
    photo_path: str | Path,
    out: str | Path = DEFAULT_OUT,
    *,
    styles: list[str] | None = None,
    quality: QualityPreset = QualityPreset.STUDIO_HQ,
    line_source: str = "auto",
) -> tuple[Path, ContactSheetResult]:
    """Render + write the HTML contact sheet, plus a JSON metrics sidecar
    with the base64 image payloads stripped (the vision_loop.py convention)
    so numeric history is diffable without bloating the repo."""
    result = build_contact_sheet(photo_path, styles=styles, quality=quality, line_source=line_source)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_contact_sheet_html(result), encoding="utf-8")

    slim = asdict(result)
    slim.pop("source_png_b64", None)
    for row in slim.get("scores", []):
        row.pop("preview_png_b64", None)
    sidecar = out.parent / (out.stem + ".json")
    sidecar.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    return out, result
