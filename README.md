# BotDraw

Software-first multi-bot pen plotter platform with a high-fidelity **emulator**.

Internal product names: **BotDraw** core, **GenArtBot**, **PortraitBot**, **LettersBot**, **R&D Lab**.

## Quick start

```bash
cd /path/to/repo
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
botdraw styles
botdraw render --style stipple --seed 42
botdraw serve --port 8080
```

Open `http://127.0.0.1:8080` — **Dev Lab** UI for vectorization, palette layers, and JSON export.

### Dev Lab
- Left: style + render settings (paper, quality, seed, density, pen speeds) + established palettes
- Center: emulator with play/pause and pen-up ghost
- Right: **Layers** (solo/hide passes), **JSON** inspector, **Job** dump
- Export bar: pack / settings / layers / motion / palette JSON; import settings JSON before render
- **Palettes** tab: edit pens (color, width, opacity, nib) and save as a new preset

### Upload an image
- **GenArtBot / PortraitBot / R&D Lab:** use **Upload image** in the left panel, pick a style, then render.
- **Tools:** optional WAV upload for audio → vector.
- **CLI:** `botdraw render --style stipple --image ./photo.jpg`

## Apps

| App | Purpose |
|---|---|
| GenArtBot | Multicolor generative + technical + brick/weave/spiral styles |
| PortraitBot | Multi-style portrait gallery (linework, squiggle, pen, shade, pointillism, dots, cubism, hatch, TSP) |
| LettersBot | EN/HI/PA/UR letters, wedding/Bollywood draft flow, guest quotes, highlight passes |
| R&D Lab | Experimental motifs + rotating-base kinematics in the emulator |

## Deploy / mini-PC host (Ubuntu)

Single portable always-on box (home or venue). Local **Ollama** is installed up front; Hermes uses **Claude Max** as primary.

```bash
# on the mini-PC after first SSH
sudo mkdir -p /opt/botdraw && sudo chown "$USER":"$USER" /opt/botdraw
git clone https://github.com/TheForgeCorp/BotDraw.git /opt/botdraw
cd /opt/botdraw
sudo ./scripts/bootstrap_minipc.sh
hermes model   # interactive: authenticate Claude Max
```

Full runbook: [`docs/host/UBUNTU_MINIPC.md`](docs/host/UBUNTU_MINIPC.md) · hardware: [`docs/ops/HARDWARE.md`](docs/ops/HARDWARE.md) · venue plotter: [`docs/host/PLOTTER_NODE.md`](docs/host/PLOTTER_NODE.md)

Venue / remote plotter node (home Hermes stays up; **no plotter required for E2E**):

```bash
export BOTDRAW_API=http://botdraw-home:8080   # Tailscale address
botdraw plot-worker --driver stub             # E2E remote test; later: axidraw
```

Optional sync-from-laptop (BotDraw app only):

```bash
export BOTDRAW_HOST=your-mini-pc.local
export BOTDRAW_USER=ubuntu
./botdraw/scripts/deploy_ssh.sh
```

## CLI highlights

- `botdraw palette list` / `botdraw palette calibrate ...`
- `botdraw bench --style stipple --profile booth-balanced`
- Motion plan schema: `botdraw/schemas/motion_plan.schema.json`

## Ops / agent governance

- [`docs/ops/`](docs/ops/) — charter, roles, channels (web/IG/Etsy), capabilities 1–28, governance, escalation  
- Autonomy **v2**: agent runs website, Instagram (post+reply), Etsy shop(s), and stack upkeep  
- **Hermes + Claude Max** + local **Ollama**; human only: **confirm booking dates**, **cash collection**, **phone calls**  
- Hermes starter skills: [`docs/ops/hermes/skills/`](docs/ops/hermes/skills/)  
- Agents should load [`docs/ops/OPERATOR_CHARTER.md`](docs/ops/OPERATOR_CHARTER.md) + [`docs/ops/CAPABILITIES.md`](docs/ops/CAPABILITIES.md)

## Notes

- No physical plotter required for the MVP PoC.
- AxiDraw real driver is stubbed; hardware integration hooks live under `botdraw/plotter/axidraw`.
- Local LLM for LettersBot uses Ollama when available; otherwise templates.
