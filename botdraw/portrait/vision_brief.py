"""
``botdraw vision brief <job_id>``: emit a ready-to-paste folder for the
manual subscription vision workflow (no API key needed).

Why this exists: the ``manual`` provider (paste a photo into your Claude/
ChatGPT chat, save the JSON reply to disk) already works in code —
``resolve_manual_turn_path`` / ``load_manual_turn`` in claude_review.py —
but using it required exporting images by hand, setting several env vars,
and reading the ``SCENE_SYSTEM`` / ``STRUCTURE_CRITIQUE_SYSTEM`` /
``CRITIQUE_SYSTEM`` prompt text out of Python source because
``docs/vision/prompts/*.md`` are unusable four-line stubs that just point
back at that same source. This command turns that into one folder: the
exact prompt, the images to attach, and a save-the-reply-here filename
that already matches what ``BOTDRAW_VISION_TURNS_DIR`` expects.
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from botdraw.core.jobs import artifact_dir, load_job
from botdraw.core.models import LayeredSVG, PaletteSet

# (kind, system prompt, user prompt) per 1-indexed turn — mirrors the
# scene → structure critique → confirm critique flow in claude_review.py /
# vision_loop.py. Turn 3 reuses the same JSON shape as turn 2 (CRITIQUE_SYSTEM
# vs STRUCTURE_CRITIQUE_SYSTEM differ only in what they're critiquing).
_TURN_KIND = {1: "scene", 2: "critique", 3: "critique"}
_TURN_USER_PROMPT = {
    1: "Analyze this portrait photo for pen-plotter ingest. JSON only.",
    2: "Critique this structure preview against the source photo. JSON only.",
    3: "Critique this render against the source photo. JSON only.",
}


def _system_prompt_for_turn(turn: int) -> str:
    from botdraw.portrait.claude_review import CRITIQUE_SYSTEM, SCENE_SYSTEM, STRUCTURE_CRITIQUE_SYSTEM

    if turn == 1:
        return SCENE_SYSTEM
    if turn == 2:
        return STRUCTURE_CRITIQUE_SYSTEM
    return CRITIQUE_SYSTEM


def render_preview_png(
    layered: LayeredSVG, palette: PaletteSet, *, max_side: int = 480
) -> bytes:
    """
    True-color raster of a rendered job, at plotted pen widths. Every
    LayeredSVG pass renders with fill="none" (see core/svg.py), so
    redrawing polylines at pen color/width reproduces exactly what the
    plotter draws — no SVG renderer needed.
    """
    px_per_mm = max_side / max(layered.width_mm, layered.height_mm)
    w_px = max(1, int(round(layered.width_mm * px_per_mm)))
    h_px = max(1, int(round(layered.height_mm * px_per_mm)))
    img = Image.new("RGB", (w_px, h_px), (247, 241, 232))
    draw = ImageDraw.Draw(img)
    for p in layered.passes:
        try:
            pen = palette.pen_by_id(p.pen_id)
        except KeyError:
            continue
        h = pen.color_hex.lstrip("#")
        color = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        width_px = max(1, int(round(pen.profile.width_mm * px_per_mm)))
        for poly in p.polylines:
            pts = list(poly.points)
            if not pts:
                continue
            if poly.closed and len(pts) >= 2 and pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            xy = [(x * px_per_mm, y * px_per_mm) for x, y in pts]
            if len(xy) >= 2:
                draw.line(xy, fill=color, width=width_px)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_vision_brief(job_id: str, out: str | Path, *, turn: int = 1) -> Path:
    """
    Write a ready-to-paste folder for one manual-workflow turn against an
    already-rendered job. Returns the output directory.
    """
    if turn not in _TURN_KIND:
        raise ValueError(f"turn must be one of {sorted(_TURN_KIND)}, got {turn}")

    load_job(job_id)  # raises if the job doesn't exist — fail loud, not silent
    src_dir = artifact_dir(job_id)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    kind = _TURN_KIND[turn]
    system_prompt = _system_prompt_for_turn(turn)
    user_prompt = _TURN_USER_PROMPT[turn]
    (out / "prompt.txt").write_text(f"{system_prompt}\n\n{user_prompt}\n", encoding="utf-8")

    settings_path = src_dir / "settings.json"
    image_copied = False
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        candidate = settings.get("image_path")
        if candidate and Path(candidate).exists():
            src_img = Path(candidate)
            shutil.copy(src_img, out / f"source{src_img.suffix or '.jpg'}")
            image_copied = True

    layered_path = src_dir / "layered.json"
    palette_path = src_dir / "palette.json"
    preview_written = False
    if layered_path.exists() and palette_path.exists():
        layered = LayeredSVG.model_validate_json(layered_path.read_text(encoding="utf-8"))
        palette = PaletteSet.model_validate_json(palette_path.read_text(encoding="utf-8"))
        (out / "render_preview.png").write_bytes(render_preview_png(layered, palette))
        preview_written = True

    reply_name = f"turn{turn:02d}_{kind}.json"
    attachments = []
    if image_copied:
        attachments += [p.name for p in sorted(out.glob("source.*"))]
    if preview_written:
        attachments.append("render_preview.png")
    attach_list = "\n".join(f"   - `{name}`" for name in attachments) or "   - (no images resolved — see note below)"

    readme = f"""# Vision brief — job `{job_id}`, turn {turn} ({kind})

No API key needed. This uses your existing Claude or ChatGPT subscription
through the browser/app, then feeds the reply back into BotDraw as JSON.

1. Open a new chat with a vision-capable model (Claude, ChatGPT).
2. Attach these images from this folder:
{attach_list}
3. Paste the entire contents of `prompt.txt` as your message (system
   instructions + the one-line request together — most chat UIs don't
   have a separate system-prompt field, so just send it all as one
   message).
4. Copy the model's reply — **only the JSON**, strip any ```` ```json ````
   fences it adds — into a new file in this folder named exactly:
   `{reply_name}`
5. Point BotDraw at this folder and re-render:
   ```
   BOTDRAW_VISION_PROVIDER=manual BOTDRAW_VISION_TURNS_DIR={out} botdraw render ...
   ```
   or replay it standalone: `botdraw vision loop-demo --turns-dir {out}`

{"" if attachments else "Note: no source photo or render preview could be resolved from this job's artifacts — attach the photo you originally rendered manually."}
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    return out
