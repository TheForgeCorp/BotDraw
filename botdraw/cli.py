"""BotDraw CLI."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich import print

from botdraw.core.models import Orientation, PaperSize, QualityPreset
from botdraw.core.pipeline import render_job
from botdraw.palettes import calibrate_pen, create_palette, list_palette_ids, load_palette
from botdraw.styles import ensure_styles_loaded, list_styles

app = typer.Typer(help="BotDraw software-first plotter platform")
palette_app = typer.Typer(help="Palette set tools")
app.add_typer(palette_app, name="palette")
models_app = typer.Typer(help="Neural model weight management")
app.add_typer(models_app, name="models")
vision_app = typer.Typer(help="Vision review providers (Anthropic / OpenAI / Gemini / manual)")
app.add_typer(vision_app, name="vision")


vision_app = typer.Typer(help="Vision review providers (Anthropic / OpenAI / Gemini / manual)")
app.add_typer(vision_app, name="vision")
gold_app = typer.Typer(help="PortraitBot Phase B classic gold-set gate")
app.add_typer(gold_app, name="gold")


@gold_app.command("ensure-fixtures")
def gold_ensure_fixtures(
    force: bool = typer.Option(False, help="Rewrite PNG fixtures even if present"),
) -> None:
    """Write synthetic people/objects PNGs under tests/fixtures/portrait/gold/."""
    from botdraw.portrait.gold import ensure_gold_fixtures, gold_dir

    path = ensure_gold_fixtures(force=force)
    print(f"[green]gold fixtures[/green] → {path}")
    for p in sorted(gold_dir().rglob("*.png")):
        print(f"  {p.relative_to(gold_dir())}")


@gold_app.command("report")
def gold_report(
    out: Path = typer.Option(
        Path("docs/wireframes/portraitbot-phase-b-gold.html"),
        help="Self-contained HTML review report",
    ),
    quality: QualityPreset = typer.Option(QualityPreset.BOOTH_BALANCED, help="Ingest quality"),
) -> None:
    """Run classic gate-1 on the gold set and write an HTML review page."""
    from botdraw.portrait.gold import write_gold_report

    path, results = write_gold_report(out, quality=quality)
    passed = sum(1 for r in results if r.passed)
    print(f"[bold]{passed}/{len(results)}[/bold] passed → {path}")
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        color = "green" if r.passed else "red"
        print(f"  [{color}]{mark}[/{color}] {r.case.id} · edges={r.edge_count} hatch={r.hatch_count}")


@models_app.command("status")
def models_status() -> None:
    """Show which neural model weights are present."""
    from botdraw.portrait.neural import model_status, models_dir

    typer.echo(f"models dir: {models_dir()}")
    for name, present in model_status().items():
        typer.echo(f"  {name}: {'present' if present else 'missing'}")


@models_app.command("fetch")
def models_fetch(
    force: bool = typer.Option(False, help="Re-download even if present"),
) -> None:
    """Download neural model weights (~400 MB total, one-time)."""
    from botdraw.portrait.neural import fetch_models

    for name, result in fetch_models(force=force).items():
        typer.echo(f"  {name}: {result}")


@vision_app.command("status")
def vision_status() -> None:
    """Show which vision review providers are ready (key + package)."""
    from botdraw.portrait.claude_review import default_provider, provider_status

    status = provider_status()
    print(f"default provider: [bold]{default_provider()}[/bold]")
    for name, info in status.items():
        ready = "ready" if info.get("ready") else "not ready"
        color = "green" if info.get("ready") else "yellow"
        print(
            f"  [{color}]{name}[/{color}]: {ready} "
            f"(key={info.get('key')} package={info.get('package')} "
            f"model={info.get('model')})"
        )
        if name == "manual" and info.get("scene_json"):
            print(f"    scene_json={info['scene_json']}")


@vision_app.command("compare")
def vision_compare(
    image: Path = typer.Argument(..., help="Portrait photo to review"),
    out: Optional[Path] = typer.Option(None, help="Write JSON comparison to this path"),
    providers: Optional[str] = typer.Option(
        None,
        help="Comma-separated providers (default: all ready + status for the rest)",
    ),
) -> None:
    """
    Bake off scene reviews across providers on one photo.

    Providers without a key/package report an error entry (fail closed).
    Use BOTDRAW_VISION_PROVIDER=manual + BOTDRAW_VISION_SCENE_JSON for
    Claude subscription / chat-authored scenes while API keys are pending.
    """
    import numpy as np
    from PIL import Image

    from botdraw.portrait.claude_review import PROVIDERS, compare_providers_scene

    if not image.exists():
        raise typer.BadParameter(f"image not found: {image}")
    rgb = np.asarray(Image.open(image).convert("RGB"), dtype=np.float32)
    want = None
    if providers:
        want = [p.strip() for p in providers.split(",") if p.strip()]
        bad = [p for p in want if p not in PROVIDERS]
        if bad:
            raise typer.BadParameter(f"unknown providers: {bad}; choose from {list(PROVIDERS)}")
    results = compare_providers_scene(rgb, providers=want)  # type: ignore[arg-type]
    text = json.dumps(results, indent=2)
    print(text)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"[green]wrote {out}[/green]")


@app.command("styles")
def styles_cmd(category: Optional[str] = None):
    ensure_styles_loaded()
    for s in list_styles(category):
        print(f"[bold]{s['id']}[/bold] ({s['category']}) — {s['name']}")


@app.command("render")
def render_cmd(
    style: str = typer.Option(..., help="Style id"),
    out: Path = typer.Option(Path("jobs/artifacts/cli"), help="Output directory root ignored; uses job store"),
    palette: str = "default-6",
    paper: PaperSize = PaperSize.A4,
    orientation: Orientation = Orientation.PORTRAIT,
    quality: QualityPreset = QualityPreset.BOOTH_BALANCED,
    seed: int = 42,
    density: float = 1.0,
    image: Optional[Path] = None,
    app_name: str = "cli",
):
    job, payload, _layers = render_job(
        app=app_name,
        style_id=style,
        palette_id=palette,
        paper=paper,
        orientation=orientation,
        quality=quality,
        seed=seed,
        density=density,
        image_path=str(image) if image else None,
    )
    print(f"[green]Job {job.id} ready[/green]")
    print(f"SVG: {job.svg_path}")
    print(f"Motion: {job.motion_path}")
    print(f"ETA: {payload['stats']['estimated_time_s']:.1f}s paths={payload['stats']['stroke_count']}")


@app.command("bench")
def bench_cmd(
    style: str = "stipple",
    profile: QualityPreset = QualityPreset.BOOTH_BALANCED,
    rounds: int = 2,
):
    ensure_styles_loaded()
    times = []
    peak = 0
    for i in range(rounds):
        t0 = time.time()
        job, payload, _layers = render_job(
            app="bench",
            style_id=style,
            quality=profile,
            seed=100 + i,
        )
        dt = time.time() - t0
        times.append(dt)
        print(f"round {i+1}: {dt:.2f}s job={job.id} eta={payload['stats']['estimated_time_s']:.1f}s")
    avg = sum(times) / len(times)
    print(f"[bold]avg stylize {avg:.2f}s[/bold] profile={profile.value}")
    if profile == QualityPreset.BOOTH_BALANCED and avg > 60:
        print("[yellow]Recommendation: default event preset to booth-fast[/yellow]")


@palette_app.command("list")
def palette_list():
    for pid in list_palette_ids():
        p = load_palette(pid)
        print(f"{pid}: {p.name} ({len(p.pens)} pens)")


@palette_app.command("calibrate")
def palette_calibrate(
    palette_id: str,
    pen_id: str,
    width_mm: Optional[float] = None,
    color_hex: Optional[str] = None,
    opacity: Optional[float] = None,
    nib_type: Optional[str] = None,
):
    p = calibrate_pen(
        palette_id,
        pen_id,
        width_mm=width_mm,
        color_hex=color_hex,
        opacity=opacity,
        nib_type=nib_type,
    )
    print(f"Updated {p.id}/{pen_id}")


@app.command("serve")
def serve(host: str = "0.0.0.0", port: int = 8080):
    import uvicorn

    uvicorn.run("botdraw.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
