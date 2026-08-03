"""BotDraw CLI."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich import print

from botdraw.core.models import PaperSize, QualityPreset
from botdraw.core.pipeline import render_job
from botdraw.palettes import calibrate_pen, create_palette, list_palette_ids, load_palette
from botdraw.styles import ensure_styles_loaded, list_styles

app = typer.Typer(help="BotDraw software-first plotter platform")
palette_app = typer.Typer(help="Palette set tools")
app.add_typer(palette_app, name="palette")


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


@app.command("plot-worker")
def plot_worker_cmd(
    api: str = typer.Option(..., envvar="BOTDRAW_API", help="Home BotDraw base URL"),
    node: str = typer.Option("venue-1", envvar="BOTDRAW_PLOT_NODE"),
    driver: str = typer.Option("stub", help="stub | emulator | axidraw"),
    poll: float = typer.Option(5.0, help="Seconds between empty-queue polls"),
    speed: float = 1.0,
    cache_dir: Optional[Path] = typer.Option(None, help="Optional offline motion cache"),
    once: bool = typer.Option(False, help="Process at most one job then exit"),
):
    """Venue node: claim ready jobs from home API and plot locally."""
    from botdraw.plotter.worker import BotDrawApiClient, run_loop

    client = BotDrawApiClient(api, node_id=node)
    print(f"[cyan]plot-worker[/cyan] api={api} node={node} driver={driver}")
    run_loop(
        client,
        driver_name=driver,  # type: ignore[arg-type]
        poll_s=poll,
        speed=speed,
        cache_dir=cache_dir,
        once=once,
    )


@app.command("plot")
def plot_cmd(
    api: str = typer.Option(..., envvar="BOTDRAW_API", help="Home BotDraw base URL"),
    job_id: str = typer.Option(..., help="Job id to claim and plot"),
    node: str = typer.Option("venue-1", envvar="BOTDRAW_PLOT_NODE"),
    driver: str = typer.Option("stub", help="stub | emulator | axidraw"),
    speed: float = 1.0,
    cache_dir: Optional[Path] = None,
):
    from botdraw.plotter.worker import BotDrawApiClient, run_one

    client = BotDrawApiClient(api, node_id=node)
    result = run_one(
        client,
        job_id=job_id,
        driver_name=driver,  # type: ignore[arg-type]
        speed=speed,
        cache_dir=cache_dir,
    )
    print(json.dumps(result, indent=2, default=str))


@app.command("plot-sync")
def plot_sync_cmd(
    api: str = typer.Option(..., envvar="BOTDRAW_API"),
    out: Path = typer.Option(Path("jobs/plot-cache"), help="Local cache directory"),
    node: str = typer.Option("venue-1", envvar="BOTDRAW_PLOT_NODE"),
):
    """Download ready motion plans from home for offline booth use."""
    from botdraw.plotter.worker import BotDrawApiClient, sync_ready_jobs

    client = BotDrawApiClient(api, node_id=node)
    ids = sync_ready_jobs(client, out)
    print(f"[green]synced {len(ids)} jobs → {out}[/green]")
    for jid in ids:
        print(f"  {jid}")


if __name__ == "__main__":
    app()
