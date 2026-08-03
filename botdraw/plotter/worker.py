"""Venue plotter node — pulls jobs from a home BotDraw API and plots locally."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from botdraw.core.motion_plan import MotionPlan
from botdraw.plotter.axidraw.driver import AxiDrawDriverStub
from botdraw.plotter.emulator.driver import EmulatorDriver

DriverName = Literal["stub", "emulator", "axidraw"]


class BotDrawApiClient:
    def __init__(self, base_url: str, node_id: str = "venue-1", timeout_s: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, *, query: dict | None = None, body: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc

    def queue(self) -> list[dict]:
        return self._request("GET", "/api/plot/queue")

    def claim(self, job_id: str) -> dict:
        return self._request("POST", f"/api/plot/claim/{job_id}", query={"node": self.node_id})

    def motion(self, job_id: str) -> dict:
        return self._request("GET", f"/api/jobs/{job_id}/motion")

    def complete(self, job_id: str, result: dict | None = None) -> dict:
        return self._request(
            "POST",
            f"/api/plot/complete/{job_id}",
            query={"node": self.node_id},
            body=result or {},
        )

    def fail(self, job_id: str, error: str) -> dict:
        return self._request(
            "POST",
            f"/api/plot/fail/{job_id}",
            query={"node": self.node_id, "error": error},
        )


def make_driver(name: DriverName):
    if name == "emulator":
        return EmulatorDriver()
    if name == "axidraw":
        from botdraw.plotter.axidraw.driver import AxiDrawDriver

        return AxiDrawDriver()
    return AxiDrawDriverStub()


def plot_plan(plan: MotionPlan, *, driver_name: DriverName = "stub", speed: float = 1.0) -> dict:
    driver = make_driver(driver_name)
    driver.connect()
    try:
        return driver.plot(plan, speed_multiplier=speed)
    finally:
        driver.disconnect()


def sync_ready_jobs(client: BotDrawApiClient, out_dir: Path) -> list[str]:
    """Download motion plans for ready jobs into a local cache (offline booth safety)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for item in client.queue():
        job_id = item["id"]
        plan = client.motion(job_id)
        path = out_dir / f"{job_id}.motion.json"
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        meta = {"job": item, "synced_at": time.time()}
        (out_dir / f"{job_id}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        saved.append(job_id)
    return saved


def run_one(
    client: BotDrawApiClient,
    *,
    job_id: str | None = None,
    driver_name: DriverName = "stub",
    speed: float = 1.0,
    cache_dir: Path | None = None,
) -> dict:
    if job_id is None:
        queue = client.queue()
        if not queue:
            return {"ok": True, "skipped": True, "reason": "empty_queue"}
        job_id = queue[0]["id"]

    claimed = client.claim(job_id)
    plan_data = None
    if cache_dir:
        cached = cache_dir / f"{job_id}.motion.json"
        if cached.exists():
            plan_data = json.loads(cached.read_text(encoding="utf-8"))
    if plan_data is None:
        plan_data = client.motion(job_id)
    plan = MotionPlan.model_validate(plan_data)
    try:
        result = plot_plan(plan, driver_name=driver_name, speed=speed)
        client.complete(job_id, {"driver": driver_name, "node": client.node_id, "result": result})
        return {"ok": True, "job_id": job_id, "claimed": claimed, "result": result}
    except Exception as exc:
        client.fail(job_id, str(exc))
        raise


def run_loop(
    client: BotDrawApiClient,
    *,
    driver_name: DriverName = "stub",
    poll_s: float = 5.0,
    speed: float = 1.0,
    cache_dir: Path | None = None,
    once: bool = False,
) -> None:
    while True:
        outcome = run_one(
            client,
            driver_name=driver_name,
            speed=speed,
            cache_dir=cache_dir,
        )
        if outcome.get("skipped"):
            if once:
                return
            time.sleep(poll_s)
            continue
        if once:
            return
        time.sleep(0.5)
