"""Job persistence and seed-locked history."""

from __future__ import annotations

import json
import time
from pathlib import Path

from botdraw.core.models import JobRecord, JobStatus

JOBS_DIR = Path(__file__).resolve().parents[2] / "jobs" / "records"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "jobs" / "artifacts"


def ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def artifact_dir(job_id: str) -> Path:
    ensure_dirs()
    path = ARTIFACTS_DIR / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_job(job: JobRecord) -> Path:
    ensure_dirs()
    job.updated_at = time.time()
    if not job.created_at:
        job.created_at = job.updated_at
    path = JOBS_DIR / f"{job.id}.json"
    path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_job(job_id: str) -> JobRecord:
    path = JOBS_DIR / f"{job_id}.json"
    return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))


def list_jobs(limit: int = 50) -> list[JobRecord]:
    ensure_dirs()
    files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [JobRecord.model_validate_json(p.read_text(encoding="utf-8")) for p in files[:limit]]


def update_job_status(job_id: str, status: JobStatus, **fields) -> JobRecord:
    job = load_job(job_id)
    data = job.model_dump()
    data.update(fields)
    data["status"] = status
    updated = JobRecord.model_validate(data)
    save_job(updated)
    return updated
