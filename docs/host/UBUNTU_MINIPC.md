# Ubuntu mini-PC install runbook

For a **new** BotDraw host. All steps are captured here and in [`scripts/bootstrap_minipc.sh`](../../scripts/bootstrap_minipc.sh) so you can reproduce on the next node.

## 0. Assumptions

- Ubuntu 22.04 or 24.04 Server/Desktop  
- User with `sudo` (default examples use `ubuntu`)  
- Machine meets [HARDWARE.md](../ops/HARDWARE.md) (32 GB RAM target with local AI)  
- Internet available for packages, Ollama models, Hermes, Claude Max  

## 1. First SSH

If Claude Code (or a human) is connecting remotely, collect Phase 0 answers from **[GO.md](../../GO.md)** first (host IP/Tailscale name, SSH user, key or password, sudo). Do not invent credentials.

From your laptop / Claude Code host:

```bash
ssh ubuntu@<mini-pc-ip-or-hostname>
```

Optional but recommended: install Tailscale later so venue/home SSH stays easy.

## 2. Get the repo on the box

```bash
sudo mkdir -p /opt/botdraw
sudo chown "$USER":"$USER" /opt/botdraw
git clone https://github.com/TheForgeCorp/BotDraw.git /opt/botdraw
cd /opt/botdraw
# use the branch that has host scripts if not yet on main:
# git checkout cursor/ops-governance-b29d
```

Or rsync from a machine that already has the repo:

```bash
rsync -az --exclude .venv --exclude jobs/artifacts ./ ubuntu@host:/opt/botdraw/
```

## 3. Bootstrap (idempotent)

```bash
cd /opt/botdraw
sudo ./scripts/bootstrap_minipc.sh
```

What it does:

1. `apt` packages  
2. Installs **Ollama** if missing; enables `ollama` service  
3. Pulls local model(s) (`llama3.2:3b`, and `llama3.1:8b` if RAM ≥ 28 GB)  
4. Creates BotDraw `.venv`, `pip install -e .`  
5. Installs systemd units: `botdraw.service`, env file `/etc/botdraw/botdraw.env`  
6. Installs **Hermes** via official installer (non-interactive where possible)  
7. Writes `/etc/botdraw/README.local` with next steps  

Re-run safely after git pulls to refresh the venv and units.

### Useful env overrides

```bash
sudo BOTDRAW_OLLAMA_MODEL=llama3.1:8b \
     BOTDRAW_PORT=8080 \
     BOTDRAW_USER=ubuntu \
     ./scripts/bootstrap_minipc.sh
```

## 4. Hermes + Claude Max (interactive once)

Bootstrap cannot finish OAuth for you. On the mini-PC:

```bash
hermes model
# choose Anthropic / Claude Max — complete browser or device auth
```

Point Hermes at ops docs as soul/context (exact flag/config varies by Hermes version):

- `/opt/botdraw/docs/ops/OPERATOR_CHARTER.md`  
- `/opt/botdraw/docs/ops/CAPABILITIES.md`  
- `/opt/botdraw/docs/ops/GOVERNANCE.md`  

Configure Ollama as a **secondary** provider (fallback / local letters / offline experiments):

- Base URL: `http://127.0.0.1:11434`  
- Model: whatever you pulled (see `ollama list`)  

## 5. Verify

```bash
systemctl status ollama botdraw --no-pager
curl -s http://127.0.0.1:11434/api/tags | head
curl -s http://127.0.0.1:8080/api/health
# expect llm_loaded true after LettersBot hits Ollama at least once
botdraw styles | head
```

Open Dev Lab: `http://<mini-pc>:8080`

## 6. Day-2 ops

```bash
cd /opt/botdraw && git pull
sudo ./scripts/bootstrap_minipc.sh   # refresh deps/units
sudo systemctl restart botdraw
```

Logs:

```bash
journalctl -u botdraw -f
journalctl -u ollama -f
```

## 7. Second / Nth node (expansion)

Same procedure: clone → `bootstrap_minipc.sh` → `hermes model`.  
Keep shop credentials and secrets **out of git**; copy `/etc/botdraw/` secrets with your own secure channel.

## 8. Deploy-from-laptop alternative

If the repo already lives on a desktop:

```bash
export BOTDRAW_HOST=botdraw.local BOTDRAW_USER=ubuntu
./botdraw/scripts/deploy_ssh.sh
```

That syncs BotDraw only. Prefer **bootstrap on the host** when standing up Ollama + Hermes the first time.
