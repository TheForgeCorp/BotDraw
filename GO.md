# GO — BotDraw mini-PC launch (for Claude Code)

**Audience:** Claude Code (or similar) running on Nav’s machine / cloud — **not** already on the mini-PC.  
**User intent:** Nav says **“go”** → you SSH in, install, verify, and wake Ink.

**Hard rule:** Do **not** SSH, clone, or install until Phase 0 answers are filled. Ask first. Wait for Nav.

---

## Phase 0 — Ask Nav (required before connect)

Copy this block (or ask each item). Do not invent answers. Do not proceed with blanks on required items.

```text
Before I connect and install BotDraw on the mini-PC, I need:

REQUIRED
1. Host reachability — how do I reach it?
   - IP address and/or hostname (LAN or Tailscale MagicDNS / 100.x)
   - Prefer: Tailscale name, LAN IP, or both
2. SSH login
   - Username (e.g. ubuntu)
   - Auth: SSH key path on this machine, OR password (you type it; I will not store it in the repo)
   - Port if not 22
3. Sudo
   - Does that user have passwordless sudo? If not, is the sudo password the same as SSH login?
4. OS readiness
   - Is Ubuntu 22.04/24.04 already installed with SSH enabled and on the network?
   - First boot done (user created, disk expanded)?

USUALLY NEEDED
5. Install path — default /opt/botdraw OK?
6. Git clone method — public HTTPS to TheForgeCorp/BotDraw OK, or private/SSH deploy key / token?
7. Git branch — main, or cursor/ops-governance-b29d until host scripts merge?
8. Service user — same as SSH user (BOTDRAW_USER)? Default ubuntu.
9. Dev Lab port — default 8080 OK? Any firewall / router rules needed for LAN access?
10. Interactive availability — will you be at a browser in the next ~15 min for `hermes model` (Claude Max auth)? If not, we stop after Phase 1 (automated install) and you auth later.

OPTIONAL / DEFER
11. Tailscale — already on the mini-PC? Install during go? Skip for now?
12. Ollama models — defaults llama3.2:3b (+ llama3.1:8b if RAM ≥ ~28GB) OK, or SKIP_OLLAMA_PULL / different tags?
13. Skip Hermes CLI install? (SKIP_HERMES=1) — only if you will install later
14. Existing /opt/botdraw or prior install to preserve?
15. Anything else (static IP, VPN, nonstandard home dir)?
```

**Stop here** until Nav answers the REQUIRED set (and enough of USUALLY NEEDED to act).

### Agent confirmation before SSH

Reply to Nav with a short recap, then wait for explicit OK:

```text
I will:
- ssh <user>@<host>[:port] using <key|password>
- clone TheForgeCorp/BotDraw → <path> (branch <branch>)
- sudo ./scripts/go.sh (BOTDRAW_USER=… PORT=…)
- verify health; then pause for hermes model if you are ready

Confirm: go / wait / change …
```

---

## Phase 1 — Connect + install (automated)

Only after Phase 0 OK.

### 1. SSH in

```bash
ssh -p <port> <user>@<host>
```

If Claude Code’s remote/SSH session is already the way in: open that host, then continue in the remote shell.

### 2. Repo on disk (if missing)

```bash
sudo mkdir -p /opt/botdraw
sudo chown "$USER":"$USER" /opt/botdraw
git clone https://github.com/TheForgeCorp/BotDraw.git /opt/botdraw
cd /opt/botdraw
# Until host/go scripts are on main:
# git fetch origin && git checkout cursor/ops-governance-b29d
```

If the clone already exists: `cd /opt/botdraw && git pull` (correct branch).

### 3. Run go

```bash
cd /opt/botdraw
sudo BOTDRAW_USER=<ssh-user> BOTDRAW_PORT=8080 ./scripts/go.sh
```

Idempotent. Safe to re-run after `git pull`.

### 4. Verify (do not skip)

```bash
systemctl is-active botdraw ollama
curl -sf http://127.0.0.1:8080/api/health
curl -sf http://127.0.0.1:11434/api/tags | head
```

### 5. Report to Nav

- Dev Lab: `http://<lan-or-tailscale-ip>:8080`
- `systemctl` status for `botdraw` / `ollama`
- Failures + what Nav must do next (auth, firewall, Tailscale)

---

## Phase 2 — Interactive (Nav once)

Needs Nav at a browser / device prompt:

```bash
sudo -u <BOTDRAW_USER> -i
hermes model    # Anthropic / Claude Max
```

Then wire Ink (skills symlink is attempted by `go.sh`; paste boot prompt from `docs/ops/hermes/README.md`).

---

## Out of scope for first “go”

- Buying plotter hardware  
- Live IG/Etsy credentials  
- Venue plot-worker (see `docs/host/PLOTTER_NODE.md`)  
- Storing Nav’s passwords or API keys in git  

## Detailed references

| Doc | When |
|---|---|
| [`scripts/go.sh`](scripts/go.sh) | Install + health entrypoint |
| [`scripts/bootstrap_minipc.sh`](scripts/bootstrap_minipc.sh) | Low-level install |
| [`docs/host/UBUNTU_MINIPC.md`](docs/host/UBUNTU_MINIPC.md) | Full host runbook |
| [`docs/ops/HARDWARE.md`](docs/ops/HARDWARE.md) | Specs |
| [`docs/ops/hermes/README.md`](docs/ops/hermes/README.md) | Ink persona + boot prompt |
| [`docs/host/PLOTTER_NODE.md`](docs/host/PLOTTER_NODE.md) | Remote stub worker later |

## Success criteria

- [ ] Phase 0 answers captured; Nav confirmed connect plan  
- [ ] SSH session to mini-PC works via Claude Code  
- [ ] `botdraw` active on `:8080`  
- [ ] `ollama` active with at least one model  
- [ ] Hermes installed; Claude Max auth done (or explicitly deferred)  
- [ ] Ink boot prompt acknowledged  
- [ ] Nav can open Dev Lab from LAN or Tailscale  
