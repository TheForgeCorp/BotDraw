#!/usr/bin/env bash
# Deploy BotDraw from this desktop/repo to a single BotDraw host over SSH.
set -euo pipefail

HOST="${BOTDRAW_HOST:-botdraw.local}"
USER_NAME="${BOTDRAW_USER:-ubuntu}"
REMOTE_DIR="${BOTDRAW_DIR:-/opt/botdraw}"
SERVICE="${BOTDRAW_SERVICE:-botdraw}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Deploying $ROOT -> ${USER_NAME}@${HOST}:${REMOTE_DIR}"

ssh "${USER_NAME}@${HOST}" "sudo mkdir -p '${REMOTE_DIR}' && sudo chown ${USER_NAME}:${USER_NAME} '${REMOTE_DIR}'"

rsync -az --delete \
  --exclude '.git' \
  --exclude 'jobs/artifacts' \
  --exclude 'jobs/records' \
  --exclude '__pycache__' \
  --exclude '.venv' \
  --exclude 'node_modules' \
  "$ROOT/" "${USER_NAME}@${HOST}:${REMOTE_DIR}/"

ssh "${USER_NAME}@${HOST}" bash -s <<EOF
set -euo pipefail
cd '${REMOTE_DIR}'
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .
sudo tee /etc/systemd/system/${SERVICE}.service >/dev/null <<UNIT
[Unit]
Description=BotDraw API
After=network.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${REMOTE_DIR}
Environment=PATH=${REMOTE_DIR}/.venv/bin
ExecStart=${REMOTE_DIR}/.venv/bin/botdraw serve --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE}
sudo systemctl restart ${SERVICE}
sudo systemctl --no-pager status ${SERVICE} || true
EOF

echo "Deploy complete. Open http://${HOST}:8080"
