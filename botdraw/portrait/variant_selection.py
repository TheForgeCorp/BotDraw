"""
Best-of-N variant selection: render the same photo + style at several
seeds, then either a human or a vision model picks the one that most
resembles the source.

Why this instead of vision-as-knob-twiddling: the closed CritiqueActions
vocabulary in claude_review.py (hatch_budget_mul, density_mul, scan_mode,
...) cannot express "this specific seed's composition is better" — that's
not a knob any of today's restylers expose. Rendering several seeded
variants and picking the best one sidesteps that ceiling entirely, and
works identically whether the "picker" is a human looking at an HTML
sheet or a vision model given the same images.
"""
from __future__ import annotations

import base64
import html
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.pens import assign_pens
from botdraw.portrait.restyle import render_from_vector

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "docs" / "wireframes" / "portraitbot-variant-selection.html"


@dataclass
class Variant:
    seed: int
    path_count: int
    preview_png_b64: str = field(repr=False)


@dataclass
class SelectionResult:
    photo: str
    style_id: str
    quality: str
    generated_at: str
    source_png_b64: str = field(repr=False)
    variants: list[Variant] = field(default_factory=list)
    vision_best_index: int | None = None
    vision_reasoning: str | None = None
    vision_confidence: float | None = None


def _source_thumb_b64(photo_path: Path, max_side: int = 420) -> str:
    from PIL import Image

    img = Image.open(photo_path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def render_seeded_variants(
    photo_path: str | Path,
    style_id: str,
    *,
    n: int = 4,
    seed0: int = 1,
    quality: QualityPreset = QualityPreset.STUDIO_HQ,
    palette_id: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    line_source: str = "auto",
) -> tuple[list[Variant], list[bytes]]:
    """
    Render the same photo/style at seeds seed0..seed0+n-1. Ingests once
    (ingest is not seed-sensitive here — only style rendering is) and
    reuses the PortraitVector across variants for speed.

    Returns (Variant metadata list, raw preview PNG bytes list) — the
    bytes are kept separate from the dataclass so callers doing a vision
    call don't have to re-decode base64.
    """
    from botdraw.portrait.vision_brief import render_preview_png

    palette = load_palette(palette_id)
    pv = ingest_portrait(str(photo_path), mode="photo", quality=quality, paper=paper, line_source=line_source)
    pv = assign_pens(pv, palette)

    variants: list[Variant] = []
    preview_bytes: list[bytes] = []
    for i in range(max(1, n)):
        seed = seed0 + i
        params = StyleParams(seed=seed, quality=quality, density=1.0)
        layered = render_from_vector(style_id, pv, palette, params)
        png = render_preview_png(layered, palette, max_side=420)
        preview_bytes.append(png)
        path_count = sum(len(p.polylines) for p in layered.passes)
        variants.append(
            Variant(seed=seed, path_count=path_count, preview_png_b64=base64.b64encode(png).decode("ascii"))
        )
    return variants, preview_bytes


def render_selection_html(result: SelectionResult) -> str:
    photo_name = html.escape(Path(result.photo).name)
    cards = []
    for i, v in enumerate(result.variants):
        picked = result.vision_best_index == i
        badge = '<span class="badge pick">VISION PICK</span>' if picked else ""
        cards.append(
            f"""
<article class="card{' is-pick' if picked else ''}">
  <header><h2>Seed {v.seed}</h2>{badge}</header>
  <figure><img src="data:image/png;base64,{v.preview_png_b64}" alt="seed {v.seed} render"/></figure>
  <div class="meta"><span>paths</span><strong>{v.path_count}</strong></div>
</article>
"""
        )
    vision_block = ""
    if result.vision_best_index is not None:
        vision_block = f"""
<p class="lede">Vision picked seed {result.variants[result.vision_best_index].seed}
(confidence {result.vision_confidence:.2f}): {html.escape(result.vision_reasoning or '')}</p>
"""
    else:
        vision_block = '<p class="lede">No vision provider ready — pick your favorite by eye below.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>PortraitBot variant selection — {photo_name}</title>
<style>
  :root {{
    --ink: #1d1d1f; --muted: #6e6e73; --faint: #8e8e93; --line: #d2d2d7;
    --panel: #ffffff; --soft: #f5f5f7; --bg: #ececef; --ok: #1f7a3f;
    --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: var(--font); color: var(--ink);
    background: linear-gradient(180deg, #f7f7f8 0%, var(--bg) 40%, #e8e8eb 100%); line-height: 1.45; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
  header.hero {{ display: flex; gap: 1.5rem; align-items: flex-start; margin-bottom: 1.5rem; padding-bottom: 1.25rem; border-bottom: 1px solid var(--line); }}
  header.hero figure {{ margin: 0; flex: none; width: 140px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
  header.hero img {{ display: block; width: 100%; height: auto; }}
  .eyebrow {{ margin: 0; font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); font-weight: 600; }}
  h1 {{ margin: 0.15rem 0 0.5rem; font-size: clamp(1.3rem, 3vw, 1.7rem); letter-spacing: -0.03em; }}
  .lede {{ margin: 0; color: var(--muted); font-family: var(--mono); font-size: 0.85rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }}
  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 0.85rem; }}
  .card.is-pick {{ border-color: var(--ok); box-shadow: 0 0 0 2px rgba(31,122,63,0.15); }}
  .card header {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .card h2 {{ margin: 0; font-size: 0.95rem; }}
  .card figure {{ margin: 0.6rem 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--soft); }}
  .card img {{ display: block; width: 100%; height: auto; }}
  .meta {{ font-family: var(--mono); font-size: 0.72rem; color: var(--faint); }}
  .meta strong {{ color: var(--ink); }}
  .badge.pick {{ background: #e5f5ea; color: var(--ok); padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.65rem; font-weight: 700; }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <figure><img src="data:image/png;base64,{result.source_png_b64}" alt="source"/></figure>
    <div>
      <p class="eyebrow">PortraitBot variant selection</p>
      <h1>{photo_name} — {html.escape(result.style_id)}</h1>
      <p class="lede">quality={html.escape(result.quality)} · generated {html.escape(result.generated_at)}</p>
      {vision_block}
    </div>
  </header>
  <div class="grid">{''.join(cards)}</div>
</div>
</body>
</html>
"""


def write_selection_sheet(
    photo_path: str | Path,
    out: str | Path = DEFAULT_OUT,
    *,
    style_id: str,
    n: int = 4,
    seed0: int = 1,
    quality: QualityPreset = QualityPreset.STUDIO_HQ,
    use_vision: bool = False,
    vision_provider: str | None = None,
) -> tuple[Path, SelectionResult]:
    """
    Render N seeded variants, optionally ask a vision provider to rank
    them (use_vision=True; no-op/fails closed with no provider ready —
    see select_best_variant), and write the committed HTML sheet + JSON
    metrics sidecar (gold.py / vision_loop.py / scoreboard.py convention).
    """
    photo_path = Path(photo_path)
    variants, preview_bytes = render_seeded_variants(
        photo_path, style_id, n=n, seed0=seed0, quality=quality
    )

    vision_best_index = None
    vision_reasoning = None
    vision_confidence = None
    if use_vision:
        import numpy as np
        from PIL import Image

        from botdraw.portrait.claude_review import select_best_variant

        source_rgb = np.asarray(Image.open(photo_path).convert("RGB"), dtype=np.float32)
        selection = select_best_variant(source_rgb, preview_bytes, provider=vision_provider)
        if selection is not None:
            vision_best_index = selection.best_index
            vision_reasoning = selection.reasoning
            vision_confidence = selection.confidence

    result = SelectionResult(
        photo=str(photo_path),
        style_id=style_id,
        quality=quality.value if isinstance(quality, QualityPreset) else str(quality),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_png_b64=_source_thumb_b64(photo_path),
        variants=variants,
        vision_best_index=vision_best_index,
        vision_reasoning=vision_reasoning,
        vision_confidence=vision_confidence,
    )

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_selection_html(result), encoding="utf-8")

    slim = asdict(result)
    slim.pop("source_png_b64", None)
    for row in slim.get("variants", []):
        row.pop("preview_png_b64", None)
    (out.parent / (out.stem + ".json")).write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    return out, result
