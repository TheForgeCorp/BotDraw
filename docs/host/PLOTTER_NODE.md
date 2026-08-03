# Venue plotter node (home brain stays up)

Keep **Hermes + BotDraw + Ollama on the home mini-PC**. At venues, run a thin **plotter node** that only pulls motion plans and drives the USB plotter. Do not unplug the home box.

```text
HOME (always on)
  Hermes · botdraw.service · Ollama · jobs store
       │ Tailscale / LAN
       ▼
VENUE laptop or small PC
  botdraw plot-worker · AxiDraw USB (or stub/emulator while testing)
```

## Testing posture (no plotter yet)

We validate the **whole remote setup end-to-end without hardware**:

- Home (or any always-on PC): `botdraw serve` + optional Hermes  
- Remote PC (any laptop): Tailscale → `botdraw plot-worker --driver stub` (or `emulator`)  
- No AxiDraw required until hardware arrives  

`--driver stub` claims/completes jobs and logs “would plot.”  
`--driver emulator` replays timing locally.  
`--driver axidraw` is for real USB later.

Any PC can be the venue node in remote mode; it does not need to be the eventual booth laptop.

## Roles

| Machine | Runs | Does not run |
|---|---|---|
| Home mini-PC | Hermes, BotDraw API, Ollama, commerce | Physical plotter |
| Venue / remote test PC | `botdraw plot-worker`, stub or plotter drivers | Hermes, Claude Max, IG/Etsy daemons |

## Setup venue / remote test node

```bash
# once — clone same repo (or rsync without .venv)
git clone https://github.com/TheForgeCorp/BotDraw.git ~/botdraw-plotter
cd ~/botdraw-plotter
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Tailscale both machines; note home MagicDNS / 100.x address
export BOTDRAW_API=http://botdraw-home:8080
# or: http://100.x.x.x:8080
```

No plotter packages needed for stub/emulator E2E. Install `pyaxidraw` (etc.) only when hardware is live.

## Run worker (E2E remote test = stub)

Poll home queue and plot the next claimed job:

```bash
export BOTDRAW_API=http://botdraw-home:8080
export BOTDRAW_PLOT_NODE=remote-test-1
botdraw plot-worker --driver stub --poll 5
```

Single job:

```bash
botdraw plot --job-id <id> --driver stub
# later hardware: --driver axidraw
```

## Job state machine (cross-node)

```text
ready ──claim──► plotting ──complete──► done
                    │
                    └──fail──► ready | failed
```

Home API endpoints used by the worker:

- `GET  /api/plot/queue` — jobs with `status=ready` and a motion plan  
- `POST /api/plot/claim/{job_id}?node=venue-laptop-1`  
- `GET  /api/jobs/{job_id}/motion` — motion plan JSON  
- `POST /api/plot/complete/{job_id}?node=...`  
- `POST /api/plot/fail/{job_id}?node=...&error=...`  

Unique physical plots stay locked via `plotting` so two venues cannot claim the same job.

## Before you leave home (WAN risk)

```bash
# optional cache of ready packs onto venue disk
botdraw plot-sync --api http://botdraw-home:8080 --out ~/plot-cache
```

If Tailscale dies at the booth, plot from `--cache-dir` offline, then complete/fail when back online.

## Hermes

Hermes stays on home. On Telegram: “plot job X at venue” → home marks ready / notifies; venue worker picks it up. No second Hermes required.
