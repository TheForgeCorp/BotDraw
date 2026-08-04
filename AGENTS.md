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

## Vision review (optional studio loop)

A vision model reviews the photo (scene knobs) and optionally critiques one render.
It does **not** generate strokes — U2-Net / mesh / restyle stay the drawing path.

Providers (`BOTDRAW_VISION_PROVIDER`, default `anthropic`):

| Provider | Env key | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | Claude API |
| `openai` | `OPENAI_API_KEY` | GPT vision |
| `gemini` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Gemini vision |
| `manual` | `BOTDRAW_VISION_SCENE_JSON` | Chat/subscription-authored scene JSON on disk (no API key) |

- Install: `pip install -e ".[vision]"` (anthropic + openai + google-genai SDKs).
- Model overrides: `BOTDRAW_CLAUDE_MODEL`, `BOTDRAW_OPENAI_MODEL`, `BOTDRAW_GEMINI_MODEL`.
- CLI: `botdraw vision status` · `botdraw vision compare photo.jpg --out compare.json`
- Module: `botdraw/portrait/claude_review.py` — `review_photo`, `critique_render`,
  `compare_providers_scene`, closed `fix`/`actions` dictionaries mapped onto real knobs.
- Dev Panel: “AI review (Studio)” checkbox → `ai_review=true` on ingest/render.
- Booth default: off. Fail closed when key/package/API missing.
- While API keys are pending, use Claude (subscription/chat) scenes via `manual` +
  a JSON file; bake off OpenAI/Gemini with `vision compare` once keys are set.
- Scene JSON is saved next to ingest artifacts as `ai_scene.json` when present.
- Unit tests mock the vision client; CI never calls live APIs.
