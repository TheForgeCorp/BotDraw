#!/usr/bin/env bash
# Bootstrap a BotDraw + Ollama (+ Hermes) Ubuntu mini-PC host from this repo.
# Idempotent: safe to re-run after git pull.
#
# Usage (on the mini-PC):
#   cd /opt/botdraw
#   sudo ./scripts/bootstrap_minipc.sh
#
# Env overrides:
#   BOTDRAW_USER=ubuntu
#   BOTDRAW_DIR=/opt/botdraw
#   BOTDRAW_PORT=8080
#   BOTDRAW_OLLAMA_MODEL=llama3.2:3b
#   BOTDRAW_OLLAMA_EXTRA_MODEL=llama3.1:8b
#   SKIP_HERMES=1
#   SKIP_OLLAMA_PULL=1
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

BOTDRAW_USER="${BOTDRAW_USER:-ubuntu}"
BOTDRAW_DIR="${BOTDRAW_DIR:-/opt/botdraw}"
BOTDRAW_PORT="${BOTDRAW_PORT:-8080}"
BOTDRAW_OLLAMA_MODEL="${BOTDRAW_OLLAMA_MODEL:-llama3.2:3b}"
BOTDRAW_OLLAMA_EXTRA_MODEL="${BOTDRAW_OLLAMA_EXTRA_MODEL:-llama3.1:8b}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${REPO_DIR}/pyproject.toml" ]]; then
  echo "Cannot find BotDraw repo root near ${SCRIPT_DIR}" >&2
  exit 1
fi

# Prefer explicit BOTDRAW_DIR if it already has the repo; else use checkout we ran from.
if [[ -f "${BOTDRAW_DIR}/pyproject.toml" ]]; then
  REPO_DIR="$(cd "${BOTDRAW_DIR}" && pwd)"
fi

echo "==> BotDraw host bootstrap"
echo "    repo:   ${REPO_DIR}"
echo "    user:   ${BOTDRAW_USER}"
echo "    port:   ${BOTDRAW_PORT}"
echo "    ollama: ${BOTDRAW_OLLAMA_MODEL}"

if ! id "${BOTDRAW_USER}" &>/dev/null; then
  echo "User ${BOTDRAW_USER} does not exist" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  ca-certificates curl git jq build-essential \
  python3 python3-venv python3-pip python3-dev \
  rsync ufw

# --- Ollama ---
if ! command -v ollama >/dev/null 2>&1; then
  echo "==> Installing Ollama"
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "==> Ollama already installed: $(command -v ollama)"
fi

systemctl enable ollama 2>/dev/null || true
systemctl start ollama 2>/dev/null || true
# Wait until API answers
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:11434/api/tags >/dev/null; then
    break
  fi
  sleep 1
done

if [[ "${SKIP_OLLAMA_PULL:-0}" != "1" ]]; then
  echo "==> Pulling Ollama model ${BOTDRAW_OLLAMA_MODEL}"
  sudo -u "${BOTDRAW_USER}" ollama pull "${BOTDRAW_OLLAMA_MODEL}" || ollama pull "${BOTDRAW_OLLAMA_MODEL}"

  MEM_GB="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
  echo "    detected RAM: ${MEM_GB} GB"
  if [[ "${MEM_GB}" -ge 28 && -n "${BOTDRAW_OLLAMA_EXTRA_MODEL}" ]]; then
    echo "==> Pulling extra model ${BOTDRAW_OLLAMA_EXTRA_MODEL}"
    sudo -u "${BOTDRAW_USER}" ollama pull "${BOTDRAW_OLLAMA_EXTRA_MODEL}" || ollama pull "${BOTDRAW_OLLAMA_EXTRA_MODEL}"
  fi
fi

# --- BotDraw app ---
echo "==> Installing BotDraw into ${REPO_DIR}"
chown -R "${BOTDRAW_USER}:${BOTDRAW_USER}" "${REPO_DIR}"
sudo -u "${BOTDRAW_USER}" bash -lc "
  set -euo pipefail
  cd '${REPO_DIR}'
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -U pip wheel
  pip install -e .
"

mkdir -p /etc/botdraw
ENV_FILE=/etc/botdraw/botdraw.env
if [[ ! -f "${ENV_FILE}" ]]; then
  cat >"${ENV_FILE}" <<EOF
# BotDraw host environment
BOTDRAW_HOST=0.0.0.0
BOTDRAW_PORT=${BOTDRAW_PORT}
OLLAMA_HOST=127.0.0.1:11434
BOTDRAW_OLLAMA_MODEL=${BOTDRAW_OLLAMA_MODEL}
EOF
  chmod 640 "${ENV_FILE}"
  chown root:"${BOTDRAW_USER}" "${ENV_FILE}"
fi

UNIT=/etc/systemd/system/botdraw.service
cat >"${UNIT}" <<EOF
[Unit]
Description=BotDraw API + Dev Lab
After=network-online.target ollama.service
Wants=network-online.target ollama.service

[Service]
Type=simple
User=${BOTDRAW_USER}
Group=${BOTDRAW_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=-/etc/botdraw/botdraw.env
Environment=PATH=${REPO_DIR}/.venv/bin:/usr/local/bin:/usr/bin
ExecStart=${REPO_DIR}/.venv/bin/botdraw serve --host 0.0.0.0 --port ${BOTDRAW_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable botdraw
systemctl restart botdraw

# --- Hermes ---
if [[ "${SKIP_HERMES:-0}" != "1" ]]; then
  if ! command -v hermes >/dev/null 2>&1; then
    echo "==> Installing Hermes Agent (official installer)"
    # Official one-liner; may evolve — see https://github.com/NousResearch/hermes-agent
    if curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh -o /tmp/hermes-install.sh; then
      chmod +x /tmp/hermes-install.sh
      sudo -u "${BOTDRAW_USER}" bash /tmp/hermes-install.sh || bash /tmp/hermes-install.sh || {
        echo "WARN: Hermes install script failed. Install manually from https://hermes-agent.nousresearch.com/" >&2
      }
    else
      echo "WARN: Could not download Hermes install script. Install manually later." >&2
    fi
  else
    echo "==> Hermes already on PATH: $(command -v hermes)"
  fi
fi

# Firewall: allow Dev Lab if ufw active
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow "${BOTDRAW_PORT}/tcp" || true
fi

cat >/etc/botdraw/README.local <<EOF
BotDraw host bootstrap completed: $(date -Is)

Repo:    ${REPO_DIR}
Service: systemctl status botdraw
Ollama:  systemctl status ollama ; ollama list
Health:  curl -s http://127.0.0.1:${BOTDRAW_PORT}/api/health

Next (interactive):
  1. sudo -u ${BOTDRAW_USER} -i
  2. hermes model   # authenticate Claude Max (Anthropic)
  3. Load ops soul docs from ${REPO_DIR}/docs/ops/
  4. Optional: add Ollama as Hermes secondary at http://127.0.0.1:11434

Ops pack: ${REPO_DIR}/docs/ops/README.md
Host runbook: ${REPO_DIR}/docs/host/UBUNTU_MINIPC.md
EOF

chown "${BOTDRAW_USER}:${BOTDRAW_USER}" /etc/botdraw/README.local

echo "==> Done"
echo "    $(cat /etc/botdraw/README.local)"
systemctl --no-pager --lines=5 status botdraw || true
