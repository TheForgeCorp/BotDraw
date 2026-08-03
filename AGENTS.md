# AGENTS.md

## Cursor Cloud specific instructions

BotDraw is a single Python (>=3.11) app: a FastAPI + Uvicorn server that also serves the static "Dev Lab" web UI, plus a Typer CLI (`botdraw`). There is no database, no Node/npm build, and no docker-compose — job data and artifacts are written to `jobs/records/` and `jobs/artifacts/`. See `README.md` for feature/CLI details.

### Environment
- The startup update script creates/uses a virtualenv at `.venv` and installs the package editable with `dev` + `optimize` extras. Activate it before running anything: `source .venv/bin/activate`.
- `python3-venv` (system package) is required to create the venv; it is installed on the base image. If venv creation ever fails with an `ensurepip` error, install `python3.12-venv` via apt.

### Run / test / lint (activate `.venv` first)
- Serve (dev): `botdraw serve --host 0.0.0.0 --port 8080`, then open `http://127.0.0.1:8080`. Use a tmux session for the long-running server. There is no separate frontend dev server and no autoreload flag wired into the CLI; restart the process to pick up code changes.
- CLI smoke test: `botdraw styles` and `botdraw render --style stipple --seed 42` (artifacts land in `jobs/artifacts/<job_id>/`).
- Tests: `pytest` (config lives in `pyproject.toml`).
- Lint: `ruff check .` — note the current codebase has many pre-existing ruff findings; a clean exit is not expected, so do not treat existing lint errors as regressions.

### API notes
- The render endpoint `POST /api/render` expects `style_id` (not `style`) in the JSON body, e.g. `{"style_id":"stipple","seed":42}`. It returns `{job, emulator, layers}` (no top-level `job_id`; the id is at `job.id`).
- `GET /api/health` returns `{"ok":true,"llm_loaded":...}`.

### Optional integrations (not needed for core E2E)
- Ollama (`:11434`) powers LettersBot LLM drafts; without it, template text is used. `vpype` (installed via the `optimize` extra) improves path-optimization metadata; a greedy fallback works without it. AxiDraw hardware is stubbed.
