#!/usr/bin/env bash
# BotDraw "go" — single entrypoint for mini-PC bring-up.
# Idempotent. Safe to re-run after git pull.
#
#   cd /opt/botdraw && sudo ./scripts/go.sh
#
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BOTDRAW_USER="${BOTDRAW_USER:-ubuntu}"
BOTDRAW_PORT="${BOTDRAW_PORT:-8080}"

if [[ ! -f "${REPO_DIR}/pyproject.toml" ]]; then
  echo "Not a BotDraw repo root: ${REPO_DIR}" >&2
  exit 1
fi

echo "=============================================="
echo " BotDraw GO — host bring-up"
echo " repo: ${REPO_DIR}"
echo " user: ${BOTDRAW_USER}"
echo "=============================================="
echo " Reminder: Claude Code should have completed"
echo " GO.md Phase 0 (ask Nav for IP/SSH/sudo) before SSH."
echo "=============================================="

# Ensure executable bits
chmod +x "${REPO_DIR}/scripts/bootstrap_minipc.sh" "${REPO_DIR}/scripts/go.sh"

# Core bootstrap (Ollama + BotDraw systemd + Hermes install attempt)
"${REPO_DIR}/scripts/bootstrap_minipc.sh"

echo ""
echo "==> Post-bootstrap verification"

ok=1
if systemctl is-active --quiet ollama; then
  echo "  [ok] ollama active"
else
  echo "  [FAIL] ollama not active"
  ok=0
fi

if systemctl is-active --quiet botdraw; then
  echo "  [ok] botdraw active"
else
  echo "  [FAIL] botdraw not active"
  ok=0
fi

if curl -sf "http://127.0.0.1:${BOTDRAW_PORT}/api/health" >/tmp/botdraw-health.json; then
  echo "  [ok] botdraw health: $(cat /tmp/botdraw-health.json)"
else
  echo "  [FAIL] botdraw health check"
  ok=0
fi

if curl -sf http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "  [ok] ollama API responding"
  sudo -u "${BOTDRAW_USER}" ollama list 2>/dev/null || ollama list || true
else
  echo "  [FAIL] ollama API"
  ok=0
fi

# Skills symlink helper (best-effort; Hermes paths vary by version)
HERMES_SKILLS_CANDIDATES=(
  "/home/${BOTDRAW_USER}/.hermes/skills"
  "/home/${BOTDRAW_USER}/.config/hermes/skills"
)
for dest_parent in "${HERMES_SKILLS_CANDIDATES[@]}"; do
  if [[ -d "$(dirname "${dest_parent}")" ]] || command -v hermes >/dev/null 2>&1; then
    mkdir -p "${dest_parent}"
    chown -R "${BOTDRAW_USER}:${BOTDRAW_USER}" "$(dirname "${dest_parent}")" 2>/dev/null || true
    link="${dest_parent}/botdraw"
    if [[ ! -e "${link}" ]]; then
      ln -sfn "${REPO_DIR}/docs/ops/hermes/skills" "${link}"
      chown -h "${BOTDRAW_USER}:${BOTDRAW_USER}" "${link}" 2>/dev/null || true
      echo "  [ok] linked skills → ${link}"
    else
      echo "  [ok] skills path exists: ${link}"
    fi
    break
  fi
done

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "=============================================="
if [[ "${ok}" -eq 1 ]]; then
  echo " GO PHASE 1 COMPLETE (automated)"
else
  echo " GO PHASE 1 FINISHED WITH FAILURES — check journalctl -u botdraw -u ollama"
fi
echo "=============================================="
echo ""
echo "Dev Lab:   http://${HOST_IP:-<host-ip>}:${BOTDRAW_PORT}"
echo "Local:     http://127.0.0.1:${BOTDRAW_PORT}"
echo "Health:    curl -s http://127.0.0.1:${BOTDRAW_PORT}/api/health"
echo ""
echo "GO PHASE 2 — interactive (Nav / Claude Max once):"
echo "  sudo -u ${BOTDRAW_USER} -i"
echo "  hermes model          # authenticate Claude Max"
echo ""
echo "GO PHASE 3 — wake Ink (paste into Hermes):"
echo "-----"
cat "${REPO_DIR}/docs/ops/hermes/README.md" | sed -n '/First boot prompt/,/^## Packs/p' | head -n 20
echo "-----"
echo "Full runbook: ${REPO_DIR}/GO.md"
echo "Local notes:  /etc/botdraw/README.local"
echo ""

# Write go stamp
mkdir -p /etc/botdraw
cat >/etc/botdraw/GO.stamp <<EOF
go_completed_at=$(date -Is)
repo=${REPO_DIR}
botdraw_port=${BOTDRAW_PORT}
phase1_ok=${ok}
EOF
chown "${BOTDRAW_USER}:${BOTDRAW_USER}" /etc/botdraw/GO.stamp 2>/dev/null || true

exit $((1 - ok))
