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
