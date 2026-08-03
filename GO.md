# GO — BotDraw mini-PC launch (for Claude / humans)

**Audience:** You (Claude Code or similar) SSHed into a fresh Ubuntu mini-PC with this repo.  
**User intent:** Nav says **“go”** → bring up BotDraw + Ollama + Hermes scaffolding end-to-end.

## One-liner (after repo is on disk)

```bash
cd /opt/botdraw   # or wherever this clone lives
sudo ./scripts/go.sh
```

Then finish the **interactive** bits printed at the end (`hermes model`, Ink boot prompt).

---

## If the repo is not on the box yet

```bash
sudo mkdir -p /opt/botdraw
sudo chown "$USER":"$USER" /opt/botdraw
git clone https://github.com/TheForgeCorp/BotDraw.git /opt/botdraw
cd /opt/botdraw
# Until merged to main, use the ops branch:
# git fetch origin && git checkout cursor/ops-governance-b29d
sudo ./scripts/go.sh
```

---

## What “go” must do (agent checklist)

Execute in order. Do **not** skip verification.

1. **Confirm OS** — Ubuntu 22.04/24.04, user has `sudo`, internet works.  
2. **Run** `sudo ./scripts/go.sh` from repo root (idempotent).  
   - Installs apt deps, Ollama, pulls models, BotDraw venv, `botdraw.service`, Hermes CLI attempt, health checks.  
3. **Verify**
   ```bash
   systemctl is-active botdraw ollama
   curl -sf http://127.0.0.1:8080/api/health
   curl -sf http://127.0.0.1:11434/api/tags | head
   ```
4. **Interactive (Nav must complete once)**  
   ```bash
   hermes model    # Anthropic / Claude Max auth
   ```
5. **Wire Ink** — symlink or copy skills per Hermes docs; paste boot prompt from `docs/ops/hermes/README.md`.  
6. **Report back to Nav** with:
   - Dev Lab URL `http://<host-ip>:8080`
   - service status
   - anything that failed / needs Nav (auth, Telegram, Tailscale)

## Out of scope for first “go”

- Buying plotter hardware  
- Live IG/Etsy credentials (list in handoff secrets inventory — Nav adds later)  
- Venue plot-worker (separate machine; see `docs/host/PLOTTER_NODE.md`)

## Detailed references

| Doc | When |
|---|---|
| [`scripts/go.sh`](scripts/go.sh) | The actual go entrypoint |
| [`scripts/bootstrap_minipc.sh`](scripts/bootstrap_minipc.sh) | Low-level install |
| [`docs/host/UBUNTU_MINIPC.md`](docs/host/UBUNTU_MINIPC.md) | Full host runbook |
| [`docs/ops/HARDWARE.md`](docs/ops/HARDWARE.md) | Specs |
| [`docs/ops/hermes/README.md`](docs/ops/hermes/README.md) | Ink persona + boot prompt |
| [`docs/host/PLOTTER_NODE.md`](docs/host/PLOTTER_NODE.md) | Remote stub worker later |

## Success criteria

- [ ] `botdraw` active on `:8080`  
- [ ] `ollama` active with at least `llama3.2:3b`  
- [ ] Hermes installed; Claude Max auth done  
- [ ] Ink boot prompt acknowledged  
- [ ] Nav can open Dev Lab from LAN or Tailscale  
