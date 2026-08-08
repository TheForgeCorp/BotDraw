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
| GenArtBot | Multicolor generative + technical + pattern pack (brick/weave/spiral + D3-inspired Voronoi/Delaunay/hex/contours/…) |
| Fractal | Escape-time Mandelbrot + single-stroke Hilbert/Peano/Moore/Gosper/Dragon/Lévy/Koch family |
| Design | Design Library → **Math Derived** (Rule 30, Phyllotaxis, Modular Chords, Sieve of Eratosthenes) |
| PortraitBot | Multi-style portrait gallery (linework, squiggle, pen, shade, pointillism, dots, cubism, hatch, TSP) |
| LettersBot | EN/HI/PA/UR letters, wedding/Bollywood draft flow, guest quotes, highlight passes |
| R&D Lab | Experimental motifs, **sensor → art** (CSV/JSON series, GPS, G-force), rotating-base kinematics |

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

## Pattern pack + D3 Pattern Lab + Design Library

- **GenArtBot** exposes Python `pattern` StyleEngines (Voronoi, Delaunay, hexbin, marching squares, force pack, etc.). CLI: `botdraw render --style voronoi --seed 42`.
- **Design → Math Derived** hosts equation-driven motifs: Rule 30, Phyllotaxis, Modular Chords, Sieve of Eratosthenes (`category: design`).
- **Tools → D3 Pattern Lab** runs live previews with vendored D3 (`botdraw/web/vendor/d3.min.js`), then posts polylines to `POST /api/render/polylines` for the same optimize → motion → emulator path.
- D3 is Lab-only; production plotter styles are NumPy/Python and do not depend on a JS runtime.

## Sensor → Art (R&D Lab)

Map real-world telemetry into symmetrical / asymmetrical / pattern drawings:

- **Kinds:** 1D series (temperature, metrics), GPS/XY paths, 3-axis G-force vectors
- **Modes:** `ribbon`, `mirror`, `radial`, `spiral`, `path`, `mandala`
- **GPS:** lon/lat (WGS84) is Web-Mercator projected before page fit (same formula as [gpx2svg](https://github.com/enginefeeder101/gpx2svg)); cartesian XY (`unit: mm` / out-of-range coords) skips projection
- **G-force:** magnitude / axis ribbons only — never double-integrated to position
- **UI:** R&D → Sensor → Art (demo datasets + CSV/JSON upload)
- **API:** `GET /api/rdlab/sensor/demos` · `POST /api/rdlab/sensor/demo` · `POST /api/rdlab/sensor/upload`

Example JSON:

```json
{"kind": "series", "label": "daily mean temp", "unit": "C", "values": [12.1, 11.8, 13.0]}
```

## PortraitBot: neural line detector

PortraitBot prefers a neural detection layer (U2-Net portrait lines, U2-Net
human-segmentation matte, BiSeNet face parsing) over the classic Sobel-edge
fallback — it produces substantially more recognizable portraits from real
photos. Without it, every ingest silently uses the weaker classic path.

```bash
pip install -e ".[neural]"   # onnxruntime, CPU-only
botdraw models fetch          # ~387 MB one-time download, cached in ~/.botdraw/models
botdraw models status         # confirm all three weights are present
```

If either the package or the weights are missing, ingest still works (classic
fallback) but surfaces a warning in the job's `layers.meta.line_source_warning`
(and the CLI prints it) so the gap is visible instead of silent.

## Notes

- No physical plotter required for the MVP PoC.
- AxiDraw real driver is stubbed; hardware integration hooks live under `botdraw/plotter/axidraw`.
- Local LLM for LettersBot uses Ollama when available; otherwise templates.
