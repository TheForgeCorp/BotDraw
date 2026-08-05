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
- **Library** tab: Pens (palette editor), Paper stocks, and Line ornaments
- **Tools** tab: audio → vector, handwriting, job reload, AxiDraw stub

### Upload an image
- **GenArtBot / PortraitBot / R&D Lab:** use **Upload image** in the left panel, pick a style, then render.
- **Tools:** optional WAV upload for audio → vector.
- **CLI:** `botdraw render --style stipple --image ./photo.jpg`

## Apps

| App | Purpose |
|---|---|
| GenArtBot | Multicolor generative + technical + brick/weave/spiral styles |
| Fractal | Escape-time Mandelbrot + single-stroke Hilbert/Peano/Moore/Gosper/Dragon/Lévy/Koch family |
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
