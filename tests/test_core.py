import json
from pathlib import Path

from botdraw.core.motion_plan import SCHEMA_VERSION, compile_motion_plan
from botdraw.core.models import StyleParams, PaperSize, QualityPreset
from botdraw.core.optimize import optimize_layered
from botdraw.core.overlays import OverlayPassComposer
from botdraw.core.pipeline import render_job
from botdraw.palettes import load_palette
from botdraw.styles import ensure_styles_loaded, get_style, list_styles


def test_styles_registered():
    ensure_styles_loaded()
    ids = {s["id"] for s in list_styles()}
    assert "stipple" in ids
    assert "brick" in ids
    assert "portrait_cubism" in ids
    assert "hilbert" in ids


def test_overlay_highlight():
    ensure_styles_loaded()
    palette = load_palette("wedding-highlight")
    layered = get_style("abstract").render(
        palette=palette,
        params=StyleParams(seed=1, quality=QualityPreset.BOOTH_FAST, density=0.5),
        paper=PaperSize.A5,
    )
    composer = OverlayPassComposer()
    layered = composer.highlight_spans(
        layered,
        [{"x": 20, "y": 30, "w": 40, "h": 5}],
        pen_id="highlight",
    )
    assert layered.passes[-1].kind == "highlight"
    plan = compile_motion_plan(optimize_layered(layered), palette)
    assert plan.schema_version == SCHEMA_VERSION
    assert plan.stats.pass_count >= 2


def test_render_job_reproducible(tmp_path):
    a, pa, la = render_job(app="test", style_id="blueprint", seed=99, quality=QualityPreset.BOOTH_FAST)
    b, pb, lb = render_job(app="test", style_id="blueprint", seed=99, quality=QualityPreset.BOOTH_FAST)
    assert Path(a.svg_path).read_text() == Path(b.svg_path).read_text()
    assert pa["stats"]["stroke_count"] == pb["stats"]["stroke_count"]
    assert la["pass_count"] == lb["pass_count"] >= 1


def test_export_pack_and_layers_summary():
    job, payload, layers = render_job(
        app="test",
        style_id="hatch",
        palette_id="default-6",
        seed=7,
        quality=QualityPreset.BOOTH_FAST,
        density=0.7,
    )
    out = Path(job.preview_path).parent
    assert (out / "export_pack.json").exists()
    assert (out / "layers.json").exists()
    assert (out / "settings.json").exists()
    pack = json.loads((out / "export_pack.json").read_text())
    assert set(pack) >= {"settings", "job", "layers", "palette", "motion_plan", "stats"}
    assert layers["pass_count"] >= 2
    assert all("color_hex" in p and "pen_id" in p for p in layers["passes"])
    assert payload["layers"]["pass_count"] == layers["pass_count"]
    assert any(seg.get("pass_id") for seg in payload["segments"])


def test_plot_queue_claim_complete():
    from fastapi.testclient import TestClient

    from botdraw.api.main import app
    from botdraw.core.jobs import load_job
    from botdraw.core.models import JobStatus

    job, _payload, _layers = render_job(
        app="test",
        style_id="blueprint",
        seed=3,
        quality=QualityPreset.BOOTH_FAST,
    )
    client = TestClient(app)
    queue = client.get("/api/plot/queue").json()
    assert any(item["id"] == job.id for item in queue)

    claimed = client.post(f"/api/plot/claim/{job.id}", params={"node": "venue-test"}).json()
    assert claimed["status"] == JobStatus.PLOTTING.value
    assert claimed["params"]["plot_node"] == "venue-test"

    conflict = client.post(f"/api/plot/claim/{job.id}", params={"node": "other-node"})
    assert conflict.status_code == 409

    done = client.post(
        f"/api/plot/complete/{job.id}",
        params={"node": "venue-test"},
        json={"driver": "stub"},
    ).json()
    assert done["status"] == JobStatus.DONE.value
    assert load_job(job.id).status == JobStatus.DONE


def test_motion_schema_file_exists():
    schema = Path(__file__).resolve().parents[1] / "botdraw" / "schemas" / "motion_plan.schema.json"
    data = json.loads(schema.read_text())
    assert data["properties"]["schema_version"]["const"] == "1.0.0"
