# Agent notes — BotDraw

## Design skills (required for UI)

Use these before designing or redesigning any frontend surface (Dev Panel **and** venue-facing):

| Skill | Path |
|-------|------|
| Impeccable | [`.cursor/skills/impeccable/SKILL.md`](.cursor/skills/impeccable/SKILL.md) |
| Taste Skill (anti-slop) | [`.cursor/skills/design-taste-frontend/SKILL.md`](.cursor/skills/design-taste-frontend/SKILL.md) |
| Minimalist UI | [`.cursor/skills/minimalist-ui/SKILL.md`](.cursor/skills/minimalist-ui/SKILL.md) |
| Redesign existing | [`.cursor/skills/redesign-existing-projects/SKILL.md`](.cursor/skills/redesign-existing-projects/SKILL.md) |
| High-end visual | [`.cursor/skills/high-end-visual-design/SKILL.md`](.cursor/skills/high-end-visual-design/SKILL.md) |

Pinned product world: [`DESIGN.md`](DESIGN.md) · [`PRODUCT.md`](PRODUCT.md).

**Letters Dev Panel** = Operate mode (tool). **Venue-facing** = Persuade mode, same tokens, more air — load impeccable `new-work` / taste-skill brief inference before building.

Sources installed from:
- https://github.com/pbakaus/impeccable
- https://github.com/Leonxlnx/taste-skill

## Neural portrait ingest (models)

Portrait ingest prefers a neural detection layer (`botdraw/portrait/neural.py`)
when onnxruntime and model weights are available; otherwise it falls back to
the classic pipeline automatically.

- Install runtime: `pip install -e ".[neural]"` (onnxruntime, CPU-only).
- Fetch weights (~400 MB one-time): `botdraw models fetch`; check with
  `botdraw models status`.
- Weights cache: `~/.botdraw/models`, overridable via `BOTDRAW_MODELS_DIR`.
- Models: U2-Net portrait (APDrawing line raster), U2-Net human seg (person
  matte), BiSeNet face parsing (CelebAMask-HQ labels). URLs + sha256 pins in
  `MODEL_SPECS`.
- CI has no weights, so tests must not require them; integration tests are
  `skipif`-gated on `neural_available()`.

## Generative portrait ink (studio)

`line_source=generative` runs a generative ink stage
(`botdraw/portrait/generative.py`) **before** contour/mesh vectorization.
Booth stays on `auto` → neural → classic.

| Provider (`BOTDRAW_GENERATIVE_PROVIDER`) | Env | Notes |
|---|---|---|
| `manual` | `BOTDRAW_GENERATIVE_INK` | PNG/JPEG line drawing on disk (subscription/chat) |
| `openai` | `OPENAI_API_KEY` | Images API edit → line drawing |
| `gemini` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini image generation |

- Fail closed → neural → classic with `line_source_warning`.
- Artifacts: `generative_ink.png`, `generative_meta.json` next to ingest.
- CLI: `botdraw generative status`.
- Fidelity: ingest-time tone correlation + one retry; meta `generative_fidelity`.
- CI mocks providers; never calls live image APIs.

## Pen Library schema (AI selection later)

`Pen` / `LineProfile` carry optional `diameter_mm`, `tip_shape`, and
`preferred_uses` (outline/shade/fill/accent). **Not wired into `assign_pens`
yet.** Future AI pen choice must emit closed `pen_map` /
`pass_overrides` only — see
[`docs/handoffs/pen-library-ai-contract.md`](docs/handoffs/pen-library-ai-contract.md).

## Vision review (live vs studio)

A vision model reviews the photo (scene knobs) and optionally critiques one render.
It does **not** generate strokes — generative ink / U2-Net / mesh / restyle stay
the drawing path.

### Modes (`ai_review`)

| Mode | Behavior |
|---|---|
| `off` | No vision (default) |
| `live` | Scene knobs only (crop / suppress / tone / protect). **No critique. No AI re-ingest.** Booth-safe. |
| `studio` | Scene + one post-render critique. Severe `keep_more_edges` may force **one** re-ingest. |

Bool `true` / `"on"` resolves by quality: `booth-*` → `live`, `studio-hq` → `studio`.

### Providers (`BOTDRAW_VISION_PROVIDER`, default `anthropic`)

| Provider | Env key | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | Claude API |
| `openai` | `OPENAI_API_KEY` | GPT vision |
| `gemini` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Gemini vision |
| `manual` | `BOTDRAW_VISION_SCENE_JSON` / `BOTDRAW_VISION_CRITIQUE_JSON` | Chat/subscription JSON on disk (no API key) |

- Install: `pip install -e ".[vision]"` (anthropic + openai + google-genai SDKs).
- Model overrides: `BOTDRAW_CLAUDE_MODEL`, `BOTDRAW_OPENAI_MODEL`, `BOTDRAW_GEMINI_MODEL`.
- CLI: `botdraw vision status` · `botdraw vision compare photo.jpg --out compare.json`
- Module: `botdraw/portrait/claude_review.py` — `resolve_ai_review_mode`, `review_photo`,
  `critique_render`, closed `fix`/`actions` dictionaries mapped onto real knobs.
- Dev Panel: **Off / Live (scene) / Studio (scene+critique)**.
- Booth never double-ingests from AI (`live` skips critique). Fail closed when key/package/API missing.
- Artifacts: `ai_scene.json` and `ai_critique.json` next to render/ingest when present.
- Unit tests mock the vision client; CI never calls live APIs.
