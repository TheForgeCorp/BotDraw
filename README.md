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

Open `http://127.0.0.1:8080`.

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

## Deploy to BotDraw host (SSH)

```bash
export BOTDRAW_HOST=your-mini-pc.local
export BOTDRAW_USER=ubuntu
./botdraw/scripts/deploy_ssh.sh
```

## CLI highlights

- `botdraw palette list` / `botdraw palette calibrate ...`
- `botdraw bench --style stipple --profile booth-balanced`
- Motion plan schema: `botdraw/schemas/motion_plan.schema.json`

## Notes

- No physical plotter required for the MVP PoC.
- AxiDraw real driver is stubbed; hardware integration hooks live under `botdraw/plotter/axidraw`.
- Local LLM for LettersBot uses Ollama when available; otherwise templates.
