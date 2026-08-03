# BotDraw host (Ubuntu mini-PC)

Single source of truth for standing up a **24/7 BotDraw + local AI + Hermes** node.

## Say “go”

From Claude Code (or a human) on the mini-PC after clone:

```bash
cd /opt/botdraw
sudo ./scripts/go.sh
```

Full agent checklist (auth, skills, Ink boot, verify): **[../../GO.md](../../GO.md)**

## Goal

On a fresh Ubuntu mini-PC (or a second node later):

```bash
ssh ubuntu@botdraw-host
git clone <this-repo> /opt/botdraw && cd /opt/botdraw
sudo ./scripts/go.sh
```

Then finish Hermes Claude Max auth once interactively (`hermes model`).

## Docs in this folder

| Doc | Purpose |
|---|---|
| [../../GO.md](../../GO.md) | **Primary** — “go” checklist for Claude SSH sessions |
| [UBUNTU_MINIPC.md](./UBUNTU_MINIPC.md) | Full install / SSH runbook (home brain) |
| [PLOTTER_NODE.md](./PLOTTER_NODE.md) | Venue / remote plotter node — E2E test with stub, no hardware |
| [../ops/HARDWARE.md](../ops/HARDWARE.md) | Specs (with local AI up front) |
| [../ops/STACK.md](../ops/STACK.md) | Hermes + Claude Max + Ollama roles |

## What gets installed

1. System packages (Python, build tools, git, curl)  
2. **Ollama** + default local model(s) — LettersBot + Hermes fallback  
3. **BotDraw** venv + `botdraw.service` (systemd)  
4. **Hermes Agent** CLI (official installer) — Claude Max primary, Ollama secondary  
5. Ops docs path wired for the agent (`docs/ops/`)  
6. Optional Tailscale note for remote SSH  

Replication = clone repo + re-run `go.sh` / bootstrap on the next machine.
