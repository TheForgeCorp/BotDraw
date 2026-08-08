# Handoff: Pen Library ↔ AI pen selection contract

**Status:** schema stub landed; selection **not wired**.  
**Audience:** whoever connects the separate Pen Library product to PortraitBot.

## Goal

AI will eventually choose **which physical pen** (marker/fineliner/etc.) should
outline vs shade a portrait pass — using rich pen metadata (size, tip shape,
diameter, preferred artistic use). Artistic **stroke geometry** stays owned by
restylers; AI only assigns pens to roles.

## Inventory (source of truth)

`PaletteSet.pens[]` in [`botdraw/core/models.py`](../../botdraw/core/models.py):

| Field | Where | Notes |
|---|---|---|
| `id`, `name`, `color_hex` | `Pen` | Existing |
| `board_id`, `lab` | `Pen` | Hardware / color distance |
| `profile.width_mm`, `nib_type`, opacity, bleed | `LineProfile` | Existing plot params |
| `profile.diameter_mm` | `LineProfile` | **New** — physical tip diameter |
| `profile.tip_shape` | `LineProfile` | **New** — `round\|chisel\|bullet\|brush\|calligraphy\|unknown` |
| `preferred_uses` | `Pen` | **New** — `outline\|shade\|fill\|accent\|any` |

Existing palette JSON keeps loading; new fields are optional with defaults.

## Closed outputs AI may emit (future)

Do **not** invent a parallel assigner. Emit only:

1. **`pen_map`** → `assign_pens(pv, palette, pen_map=...)`  
   Shape: `{ "edge" | "hatch" | <cluster_id>: <pen_id> }`  
   Hook: [`botdraw/portrait/pens.py`](../../botdraw/portrait/pens.py) +  
   `params_extra["pen_map"]` in [`botdraw/core/pipeline.py`](../../botdraw/core/pipeline.py).

2. **`pass_overrides`** (Phase 2 customization branch) →  
   `{ <stable_role>: { "pen_id": str|null, "visible": bool|null } }`  
   Applied after restyle. See `cursor/portrait-customization-ddd2`.

Vision critique (`claude_review.py`) must stay a **closed dictionary** — when
wiring, add keys like `pen_map` / `pass_overrides` to `ALLOWED_ACTION_KEYS`
only; never execute free-form model code.

## Non-goals (this contract / current PR)

- No Dev Panel AI pen picker yet
- No critique action keys for pens yet
- `assign_pens` logic unchanged — still nearest-Lab / fineliner / darkest hatch
- Generative ink (`line_source=generative`) is a separate drawing-path concern;
  pen selection applies **after** ink is vectorized

## Suggested wiring order (later)

1. Import Pen Library catalogs into `PaletteSet` JSON (fill `diameter_mm`,
   `tip_shape`, `preferred_uses`).
2. Add a studio-only AI selector that reads the palette + render roles and
   returns `pen_map` / `pass_overrides`.
3. Surface chosen pens in Dev Panel calc / job settings for operator override.
