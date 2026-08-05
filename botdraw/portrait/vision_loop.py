"""Studio vision feedback loop (3 turns) + visual pass history.

Turn 1 = pre-scene. Turn 2 = structure critique (ingest preview; at most one
re-ingest). Turn 3 = confirm (restyle knobs only; no re-ingest).
Manual/subscription JSON via BOTDRAW_VISION_TURNS_DIR.
"""

from __future__ import annotations

import base64
import html
import io
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from botdraw.core.models import QualityPreset
from botdraw.portrait.claude_review import (
    VISION_MAX_REINGESTS,
    VISION_MAX_TURNS,
    critique_render,
    critique_to_render_knobs,
    review_photo,
    scene_to_ingest_knobs,
)
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.preview import portrait_vector_raw_svg

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TURNS_DIR = REPO_ROOT / "tests" / "fixtures" / "vision" / "turns"
DEFAULT_HISTORY_HTML = REPO_ROOT / "docs" / "wireframes" / "portraitbot-vision-loop-history.html"


@dataclass
class VisionPass:
    turn: int
    kind: str  # scene | structure | confirm
    summary: str
    overall: float | None
    edge_count: int
    hatch_count: int
    knobs: dict[str, Any] = field(default_factory=dict)
    critique: dict[str, Any] | None = None
    scene: dict[str, Any] | None = None
    preview_png_b64: str | None = None
    source_png_b64: str | None = None
    reingest: bool = False


def _png_b64_from_rgb(rgb: np.ndarray, max_side: int = 360) -> str:
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def structure_preview_png(pv, *, max_side: int = 480) -> bytes:
    """Rasterize Raw SVG structure onto paper for critique + history."""
    svg = portrait_vector_raw_svg(pv)
    # Lightweight fallback: draw polylines with Pillow (no cairosvg dependency)
    w_mm, h_mm = float(pv.page_w_mm), float(pv.page_h_mm)
    scale = max_side / max(w_mm, h_mm)
    pw, ph = max(1, int(w_mm * scale)), max(1, int(h_mm * scale))
    img = Image.new("RGB", (pw, ph), (247, 241, 232))
    draw = ImageDraw.Draw(img)

    def draw_polys(polys, color, width=1):
        for pts in polys:
            if len(pts) < 2:
                continue
            xy = [(p[0] * scale, p[1] * scale) for p in pts]
            draw.line(xy, fill=color, width=width)

    draw_polys(pv.hatch_polylines_mm or [], (194, 65, 12), 1)
    draw_polys(pv.edge_polylines_mm or [], (14, 116, 144), 1)
    # Keep svg string referenced so callers can still export if needed
    _ = svg
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def ensure_manual_turn_fixtures(*, root: Path | None = None, force: bool = False) -> Path:
    """Write 3-turn subscription-shaped JSON fixtures (scene → structure → confirm)."""
    base = Path(root) if root else DEFAULT_TURNS_DIR
    base.mkdir(parents=True, exist_ok=True)
    responses = REPO_ROOT / "tests" / "fixtures" / "vision" / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    prompts = REPO_ROOT / "docs" / "vision" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    scene = {
        "orientation_deg": 0,
        "subjects": [{"kind": "other", "importance": 1.0}],
        "clutter": [],
        "lighting": "normal",
        "crop_hint": {"x": 0.12, "y": 0.08, "w": 0.76, "h": 0.84},
        "ingest": {
            "line_source": "classic",
            "suppress_background": False,
            "protect_subjects": [],
            "max_tone_code": 3,
        },
        "summary": "Object mug — classic structure gate, hatch off",
    }
    turn2 = {
        "overall": 0.42,
        "issues": [
            {
                "code": "band_sides_missing",
                "severity": 0.85,
                "region": "mug_band",
                "fix": "equalize_structure",
            },
            {
                "code": "soft_edges",
                "severity": 0.6,
                "region": "silhouette",
                "fix": "keep_more_edges",
            },
        ],
        "actions": {
            "force_reingest": True,
            "line_source": "classic",
            "scan_mode": "edges",
            "contour_simplify": 1,
            "suppress_background": False,
        },
        "summary": "Turn 2: band L/R verticals missing — equalize + finer simplify",
    }
    turn3 = {
        "overall": 0.78,
        "issues": [],
        "actions": {
            "force_reingest": False,
            "line_source": "classic",
            "density_mul": 1.0,
        },
        "summary": "Turn 3: confirm structure — accept (no further re-ingest)",
    }

    files = {
        "turn01_scene.json": scene,
        "turn02_critique.json": turn2,
        "turn03_critique.json": turn3,
    }
    for name, payload in files.items():
        path = base / name
        if force or not path.exists():
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        # Plan mirror under responses/
        alias = {
            "turn01_scene.json": "turn1_scene.json",
            "turn02_critique.json": "turn2_structure.json",
            "turn03_critique.json": "turn3_confirm.json",
        }[name]
        rpath = responses / alias
        if force or not rpath.exists():
            rpath.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Drop legacy 10-turn fixtures if regenerating
    if force:
        for stale in base.glob("turn*.json"):
            if stale.name not in files:
                stale.unlink(missing_ok=True)

    (prompts / "turn1_scene.md").write_text(
        "# Turn 1 — Scene (paste into Claude.ai with the photo)\n\n"
        "Use the BotDraw SCENE_SYSTEM schema. Prefer classic for object structure tests.\n"
        "Save JSON as BOTDRAW_VISION_SCENE_JSON or turns/turn01_scene.json.\n",
        encoding="utf-8",
    )
    (prompts / "turn2_structure.md").write_text(
        "# Turn 2 — Structure critique\n\n"
        "Paste source photo + ingest structure preview. Use STRUCTURE_CRITIQUE_SYSTEM.\n"
        "Save as BOTDRAW_VISION_CRITIQUE_JSON or turns/turn02_critique.json.\n",
        encoding="utf-8",
    )
    (prompts / "turn3_confirm.md").write_text(
        "# Turn 3 — Confirm (restyle knobs only; no re-ingest)\n\n"
        "Paste source + latest preview. Use CRITIQUE_SYSTEM. Set force_reingest false.\n"
        "Save as BOTDRAW_VISION_FEEDBACK_JSON or turns/turn03_critique.json.\n",
        encoding="utf-8",
    )
    return base


def run_vision_structure_loop(
    *,
    image_path: str | Path | None = None,
    image_array: np.ndarray | None = None,
    max_turns: int = VISION_MAX_TURNS,
    quality: str | QualityPreset = QualityPreset.BOOTH_BALANCED,
    paper: str = "A5",
    turns_dir: Path | None = None,
    case_label: str = "vision-loop",
) -> list[VisionPass]:
    """
    Run turn 1 scene + up to max_turns-1 structure critiques with re-ingest cap.

    Uses manual turn JSON when BOTDRAW_VISION_PROVIDER=manual / turns_dir set.
    """
    import os

    max_turns = max(1, min(int(max_turns), VISION_MAX_TURNS))
    prev_turns = os.environ.get("BOTDRAW_VISION_TURNS_DIR")
    prev_provider = os.environ.get("BOTDRAW_VISION_PROVIDER")
    try:
        if turns_dir is not None:
            os.environ["BOTDRAW_VISION_TURNS_DIR"] = str(turns_dir)
            os.environ.setdefault("BOTDRAW_VISION_PROVIDER", "manual")

        history: list[VisionPass] = []
        knobs: dict[str, Any] = {
            "line_source": "classic",
            "scan_mode": "edges",
            "hatch_size": 0,
            "ensemble": False,
            "contour_simplify": 2,
        }

        # --- Turn 1: scene ---
        if image_array is not None:
            rgb0 = np.asarray(image_array, dtype=np.float32)
        elif image_path is not None:
            rgb0 = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.float32)
        else:
            from botdraw.styles.image_utils import synthetic_portrait

            rgb0 = synthetic_portrait(480)

        scene = review_photo(rgb0, provider="manual")
        if scene is None:
            # Fail closed: still allow loop with classic defaults
            scene_summary = "scene unavailable — classic defaults"
            scene_dump = None
        else:
            scene_knobs = scene_to_ingest_knobs(scene)
            # Phase B classic wins unless scene explicitly classic/auto
            if scene_knobs.get("line_source") in ("classic", "auto", "neural"):
                knobs["line_source"] = (
                    "classic" if scene_knobs.get("line_source") != "neural" else "classic"
                )
            if scene_knobs.get("crop"):
                knobs["crop"] = scene_knobs["crop"]
                knobs["auto_frame"] = False
            scene_summary = scene.summary or "scene applied"
            scene_dump = scene.model_dump()

        pv = ingest_portrait(
            image_path=image_path,
            image_array=None if image_path else rgb0,
            mode="photo",
            quality=quality,
            paper=paper,
            auto_frame=knobs.get("auto_frame", True) if knobs.get("crop") is None else False,
            crop=knobs.get("crop"),
            hatch_size=0,
            line_source=knobs.get("line_source", "classic"),
            scan_mode=knobs.get("scan_mode", "edges"),
            ensemble=False,
            contour_simplify=knobs.get("contour_simplify", 2),
        )
        preview = structure_preview_png(pv)
        history.append(
            VisionPass(
                turn=1,
                kind="scene",
                summary=scene_summary,
                overall=None,
                edge_count=len(pv.edge_polylines_mm),
                hatch_count=len(pv.hatch_polylines_mm),
                knobs=dict(knobs),
                scene=scene_dump,
                preview_png_b64=base64.b64encode(preview).decode("ascii"),
                source_png_b64=_png_b64_from_rgb(np.asarray(pv.rgb, dtype=np.float32)),
                reingest=False,
            )
        )

        reingests = 0
        source_rgb = np.asarray(pv.rgb, dtype=np.float32)

        for turn in range(2, max_turns + 1):
            # Turn 3+ confirm: never re-ingest; turn 2 allows at most VISION_MAX_REINGESTS
            allow_reingest = turn < max_turns and reingests < VISION_MAX_REINGESTS
            is_confirm = turn >= max_turns
            critique = critique_render(
                source_rgb,
                preview,
                style_id="portrait_structure" if not is_confirm else "portrait_linework",
                provider="manual",
                turn=turn,
                structure=not is_confirm,
            )
            if critique is None:
                history.append(
                    VisionPass(
                        turn=turn,
                        kind="confirm" if is_confirm else "structure",
                        summary="critique unavailable — stop",
                        overall=None,
                        edge_count=len(pv.edge_polylines_mm),
                        hatch_count=len(pv.hatch_polylines_mm),
                        knobs=dict(knobs),
                        preview_png_b64=base64.b64encode(preview).decode("ascii"),
                        source_png_b64=history[0].source_png_b64,
                    )
                )
                break

            if is_confirm:
                critique.actions.force_reingest = False
            ck = critique_to_render_knobs(critique)
            if not allow_reingest:
                ck.pop("force_reingest", None)
                critique.actions.force_reingest = False

            did_reingest = False
            for key in (
                "line_source",
                "scan_mode",
                "contour_simplify",
                "suppress_background",
                "max_tone_code",
                "density_mul",
            ):
                if key in ck and ck[key] is not None:
                    knobs[key] = ck[key]

            if ck.get("force_reingest") and allow_reingest:
                did_reingest = True
                reingests += 1
                pv = ingest_portrait(
                    image_path=image_path,
                    image_array=None if image_path else rgb0,
                    mode="photo",
                    quality=quality,
                    paper=paper,
                    auto_frame=knobs.get("auto_frame", True) if knobs.get("crop") is None else False,
                    crop=knobs.get("crop"),
                    hatch_size=0,
                    line_source=knobs.get("line_source", "classic"),
                    scan_mode=knobs.get("scan_mode", "edges"),
                    ensemble=False,
                    contour_simplify=int(knobs.get("contour_simplify") or 2),
                )
                source_rgb = np.asarray(pv.rgb, dtype=np.float32)
                preview = structure_preview_png(pv)

            history.append(
                VisionPass(
                    turn=turn,
                    kind="confirm" if is_confirm else "structure",
                    summary=critique.summary or f"pass {turn}",
                    overall=float(critique.overall),
                    edge_count=len(pv.edge_polylines_mm),
                    hatch_count=len(pv.hatch_polylines_mm),
                    knobs=dict(knobs),
                    critique=critique.model_dump(),
                    preview_png_b64=base64.b64encode(preview).decode("ascii"),
                    source_png_b64=history[0].source_png_b64,
                    reingest=did_reingest,
                )
            )

        # stash label on first pass knobs for HTML
        if history:
            history[0].knobs["case_label"] = case_label
        return history
    finally:
        if prev_turns is None:
            os.environ.pop("BOTDRAW_VISION_TURNS_DIR", None)
        else:
            os.environ["BOTDRAW_VISION_TURNS_DIR"] = prev_turns
        if prev_provider is None:
            os.environ.pop("BOTDRAW_VISION_PROVIDER", None)
        else:
            os.environ["BOTDRAW_VISION_PROVIDER"] = prev_provider


def render_vision_history_html(
    history: list[VisionPass],
    *,
    title: str = "PortraitBot — Vision loop visual history",
) -> str:
    if not history:
        return "<!DOCTYPE html><html><body><p>No passes.</p></body></html>"
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    scores = [(p.turn, p.overall) for p in history if p.overall is not None]
    # Simple SVG sparkline
    spark = ""
    if len(scores) >= 2:
        w, h = 640, 120
        pts = []
        for i, (turn, ov) in enumerate(scores):
            x = 20 + (w - 40) * (i / max(1, len(scores) - 1))
            y = h - 20 - (h - 40) * float(ov)
            pts.append(f"{x:.1f},{y:.1f}")
        spark = f"""
        <svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="Overall score by pass">
          <polyline fill="none" stroke="#0e7490" stroke-width="3" points="{" ".join(pts)}"/>
          {"".join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="4" fill="#0e7490"/>' for p in pts)}
        </svg>"""

    cards = []
    for p in history:
        ov = f"{p.overall:.2f}" if p.overall is not None else "—"
        badge = "scene" if p.kind == "scene" else ("reingest" if p.reingest else p.kind)
        img = (
            f'<img src="data:image/png;base64,{p.preview_png_b64}" alt="pass {p.turn} preview"/>'
            if p.preview_png_b64
            else '<div class="empty">no preview</div>'
        )
        src = (
            f'<img src="data:image/png;base64,{p.source_png_b64}" alt="source"/>'
            if p.source_png_b64 and p.turn == 1
            else ""
        )
        cards.append(
            f"""
<article class="pass" id="pass-{p.turn}">
  <header>
    <div>
      <p class="eyebrow">Pass {p.turn} · {html.escape(badge)}</p>
      <h2>{html.escape(p.summary or "")}</h2>
    </div>
    <div class="score">
      <span class="lab">overall</span>
      <strong>{ov}</strong>
    </div>
  </header>
  <div class="grid">
    {"<figure><figcaption>Source</figcaption>" + src + "</figure>" if src else ""}
    <figure>
      <figcaption>Structure preview</figcaption>
      {img}
    </figure>
  </div>
  <div class="meta">
    <div><span>edges</span><strong>{p.edge_count}</strong></div>
    <div><span>hatch</span><strong>{p.hatch_count}</strong></div>
    <div><span>line_source</span><strong>{html.escape(str(p.knobs.get("line_source", "—")))}</strong></div>
    <div><span>scan</span><strong>{html.escape(str(p.knobs.get("scan_mode", "—")))}</strong></div>
    <div><span>simplify</span><strong>{html.escape(str(p.knobs.get("contour_simplify", "—")))}</strong></div>
    <div><span>reingest</span><strong>{"yes" if p.reingest else "no"}</strong></div>
  </div>
</article>
"""
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  :root {{
    --ink:#1d1d1f; --muted:#6e6e73; --faint:#8e8e93; --line:#d2d2d7;
    --panel:#fff; --soft:#f5f5f7; --bg:#ececef; --teal:#0e7490;
    --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; font-family:var(--font); color:var(--ink);
    background: linear-gradient(180deg,#f7f7f8 0%, var(--bg) 45%, #e8e8eb 100%);
  }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:2rem 1.25rem 4rem; }}
  h1 {{ margin:0; font-size:clamp(1.5rem,3vw,2rem); letter-spacing:-0.03em; }}
  .lede {{ color:var(--muted); max-width:62ch; }}
  .eyebrow {{ margin:0; font-size:0.7rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--faint); font-weight:600; }}
  .spark {{ width:100%; height:auto; background:var(--panel); border:1px solid var(--line); border-radius:10px; margin:1rem 0 1.5rem; }}
  .toc {{ display:flex; flex-wrap:wrap; gap:0.35rem; margin:0 0 1.25rem; }}
  .toc a {{
    text-decoration:none; color:var(--ink); border:1px solid var(--line);
    background:var(--panel); padding:0.3rem 0.5rem; border-radius:6px; font-size:0.8rem;
  }}
  .pass {{
    background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:1rem; margin:0 0 1rem;
  }}
  .pass header {{ display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; }}
  .pass h2 {{ margin:0.2rem 0 0; font-size:1.05rem; }}
  .score {{ text-align:right; font-family:var(--mono); }}
  .score .lab {{ display:block; color:var(--faint); font-size:0.65rem; }}
  .score strong {{ font-size:1.4rem; color:var(--teal); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:0.65rem; margin-top:0.75rem; }}
  figure {{ margin:0; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--soft); }}
  figcaption {{ padding:0.35rem 0.5rem; font-family:var(--mono); font-size:0.65rem; color:var(--faint); border-bottom:1px solid var(--line); }}
  figure img {{ display:block; width:100%; height:auto; background:#ddd; }}
  .meta {{
    display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0.4rem 0.6rem;
    margin-top:0.75rem; font-family:var(--mono); font-size:0.72rem;
  }}
  .meta span {{ display:block; color:var(--faint); }}
  footer {{ margin-top:1.5rem; color:var(--muted); font-size:0.85rem; }}
</style>
</head>
<body>
  <div class="wrap">
    <p class="eyebrow">BotDraw · PortraitBot · studio vision loop</p>
    <h1>{html.escape(title)}</h1>
    <p class="lede">
      Iterative improvement across {len(history)} passes (studio cap {VISION_MAX_TURNS}:
      scene → structure → confirm). Manual/subscription JSON stand-in until API key.
    </p>
    <p class="lede" style="font-family:var(--mono);font-size:0.8rem">generated {html.escape(generated)}</p>
    {spark}
    <nav class="toc">
      {"".join(f'<a href="#pass-{p.turn}">Pass {p.turn}</a>' for p in history)}
    </nav>
    {"".join(cards)}
    <footer>
      Fixtures: <code>tests/fixtures/vision/turns/</code> ·
      regenerate with <code>botdraw vision loop-demo</code>
    </footer>
  </div>
</body>
</html>
"""


def write_vision_history(
    out: Path,
    *,
    image_path: str | Path | None = None,
    max_turns: int = VISION_MAX_TURNS,
    turns_dir: Path | None = None,
) -> tuple[Path, list[VisionPass]]:
    turns = turns_dir or DEFAULT_TURNS_DIR
    ensure_manual_turn_fixtures(root=turns)
    if image_path is None:
        # Default to gold mug for structure-gap demo
        mug = REPO_ROOT / "tests" / "fixtures" / "portrait" / "gold" / "objects" / "mug.png"
        if not mug.exists():
            from botdraw.portrait.gold import ensure_gold_fixtures

            ensure_gold_fixtures()
        image_path = mug
    history = run_vision_structure_loop(
        image_path=image_path,
        max_turns=max_turns,
        turns_dir=turns,
        case_label=Path(image_path).stem,
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_vision_history_html(history), encoding="utf-8")
    # Machine-readable history without giant preview payloads
    slim = []
    for p in history:
        row = asdict(p)
        row.pop("preview_png_b64", None)
        row.pop("source_png_b64", None)
        slim.append(row)
    (out.parent / (out.stem + ".json")).write_text(
        json.dumps(slim, indent=2) + "\n",
        encoding="utf-8",
    )
    return out, history
