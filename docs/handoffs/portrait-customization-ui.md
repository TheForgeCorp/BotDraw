# 001 — Dev Panel: per-pass pen/linetype/fill customization UI

- **Status**: TODO
- **Commit**: 46d10bd (backend landed on `cursor/portrait-customization-ddd2`)
- **Severity**: MEDIUM
- **Category**: PortraitBot Dev Panel, print customization
- **Estimated scope**: ~3-4 files (`botdraw/web/app.js`, `botdraw/web/index.html`, `botdraw/web/styles.css`; possibly `botdraw/portrait/ornament.py` if per-pass linetype is included)

## Problem

The business owner asked for "a high degree of user customization for the actual rendered version that gets printed — pen setting, pen color, linetype, fill or hatch areas." Today:

- Pen color/width/opacity/nib overrides exist (`apply_pen_overrides` in `botdraw/portrait/pens.py`) but are global, per-palette-pen, not per-pass. `pen_overrides` is never populated by `botdraw/web/app.js` or `botdraw/api/main.py` — zero call sites outside `pens.py` itself.
- `portraitPenMap` is declared in `app.js`, set to `null`, and read once — no control ever assigns it.
- The existing Layers panel (`railInspector` in `app.js`) is hidden for PortraitBot (`hidden = !lab` where `lab = !letters && !portrait`), and even where visible, `setPassVisible()` in `emulator.js` only calls `drawFrame()` — it affects the canvas preview, not the exported SVG or motion plan.

None of this lets a user say "make the bands pass on my render use crimson instead of navy" or "turn off the hatch layer for this print."

## Target

A backend mechanism now exists (`cursor/portrait-customization-ddd2`, commit `46d10bd`) that this UI work is entirely additive on top of — **no further backend changes should be needed** for pen reassignment or pass visibility:

- `botdraw/core/models.py`: `PassLayer.role: str | None` + `PassLayer.stable_role()` — a semantic category (`"structure"`, `"midtone"`, `"bands"`, `"mosaic-fill"`, `"hatch"`, …) independent of which pen is currently assigned. Falls back to `id` for older passes.
- `botdraw/portrait/customization.py`: `apply_pass_overrides(layered, palette, overrides)` where `overrides = {role: {"pen_id": str | None, "visible": bool | None}}`. Invalid pen ids / unmatched roles are ignored (fail-soft).
- Wired into `render_job()` in `botdraw/core/pipeline.py` via the **existing** generic `params_extra` passthrough: `params_extra={"pass_overrides": {...}}` reaches any style (portrait or not) with zero new API endpoint fields.
- `layers_summary()` (same file) already includes `"role"` alongside `"id"` in every pass dict — this is what the API returns today at `payload["layers"]["passes"]` after any render, and what a UI should read to build controls.

The target end state for this ticket:

1. In the PortraitBot rail (or a new "Customize" section within it — see Repo conventions below for where it should live), after a render completes, list the passes from the render response (`payload.layers.passes`, each `{role, id, name, pen_id, kind, polyline_count}`) grouped by `role` (not `id`).
2. For each distinct `role`, offer:
   - A pen picker (dropdown of the active palette's pen ids/colors) → on change, sets `pendingPassOverrides[role] = {...pendingPassOverrides[role], pen_id: chosenId}`.
   - A visibility toggle (checkbox/eye icon) → on change, sets `pendingPassOverrides[role] = {...pendingPassOverrides[role], visible: checked}`.
3. A "Re-render with customization" action that calls the existing render endpoint with `params_extra: {...existingExtra, pass_overrides: pendingPassOverrides}` merged in, and re-renders.
4. Persist `pendingPassOverrides` in the job's `settings.json` round-trip (it already will, automatically, since `params_extra` is serialized into `settings["params_extra"]` in `pipeline.py` — confirm this on the actual response rather than assuming, per the drift-check rule below).

## Repo conventions to follow

- The Palette tab already has a per-pen editing pattern (color, width, opacity, nib) that saves as a new preset via `POST /api/palettes/save` — study its markup/JS structure in `app.js`/`index.html` as the visual/interaction exemplar for "add a control, wire an onChange, stage a pending value, apply on next render." Do not invent a new interaction pattern if that one fits.
- The Dev Panel's rail-group visual language is documented in `DESIGN.md` (Settings-grammar inset `.group` wells, `#f0f0f2` background + white rows, primary CTA outside the group). Read it, and the `impeccable` / `design-taste-frontend` skills per `AGENTS.md`, before writing any markup — this is a **required** step per this repo's own rules, not optional.
- Follow the existing naming: this is Dev Panel/Operate mode (a tool for the operator), not Persuade mode — compact, functional, no venue-facing polish needed here.

## Steps

1. Read `DESIGN.md` and the `impeccable`/`design-taste-frontend` skills (required by `AGENTS.md` for any Dev Panel UI work) before writing markup.
2. In `botdraw/web/app.js`, find where the render response (`payload`) is handled after a portrait render and where `portraitPenMap`/`portraitLineType` are currently read/set — add a `pendingPassOverrides` state object alongside them.
3. Add a "Passes" or "Customize" sub-section to the PortraitBot rail (`index.html` markup + `app.js` render logic), populated from `payload.layers.passes`, grouped by `role`. One row per unique role: pen swatch/dropdown + visibility toggle.
4. On any control change, update `pendingPassOverrides[role]` and mark a "customization pending — re-render to apply" affordance (do not auto-re-render on every click; batch until the user confirms, to avoid hammering the render endpoint).
5. Wire the existing render call to merge `pass_overrides: pendingPassOverrides` into whatever `params_extra` it already sends.
6. Confirm (do not assume) that `pendingPassOverrides` round-trips through `settings.json` / the job's `params_extra` on reload, per the target's point 4.

## Boundaries

- Do NOT touch `botdraw/portrait/customization.py`, `PassLayer.role`, or the `render_job()` wiring unless you find them not matching this brief (drift check below) — that backend surface is done and tested (`tests/test_pass_customization.py`, 9 tests).
- Do NOT implement per-pass **linetype** overrides in this ticket — see the separate section below for why that's out of scope here.
- Do NOT re-enable the old Layers panel's solo/hide as a substitute — it only affects the canvas preview (`emulator.js` `setPassVisible` → `drawFrame()` only), not the exported SVG/motion plan. The new `visible: false` override in `apply_pass_overrides` is the correct mechanism because it drops the pass before export.
- If the actual shape of `payload.layers.passes` or `params_extra` handling has drifted from what's described above (e.g. `role` isn't present, or `params_extra` merging changed), STOP and report the discrepancy rather than improvising around it.

## Explicitly out of scope: per-pass linetype

The plan that generated this ticket also asked for per-pass **linetype** (dashed/dotted/zigzag/etc. from `botdraw/portrait/ornament.py`'s `LINE_TYPES`). This needs real additional backend work first, not just UI:

- `ornament.decorate_layered()` today takes one global `StrokeOrnamentParams` (one `line_type`, applied via `ornament_target: "all" | "edges" | "fills" | "none"` — a coarse 3-way split, not per-role).
- Making linetype per-role would mean threading a `{role: line_type}` dict through `decorate_layered()`, likely calling `decorate_polyline()` per-pass with a different `StrokeOrnamentParams` per role instead of one shared instance.
- This is real design + implementation work (probably its own ticket), not something to bolt onto the UI ticket above. If you're picking this up next, write it as its own numbered plan in this same file/directory, following this template, before touching `ornament.py`.

## Verification

- **Mechanical**: `pytest tests/` should still pass 237+ (no backend regressions expected, since this ticket is additive-UI-only). If you touch `ornament.py` for the linetype extension, add tests following the pattern in `tests/test_stroke_ornament.py`.
- **Feel check**: run `botdraw serve`, open the Dev Panel, upload/select a portrait photo, render `Simple Linework Portrait` or `Pen Sketch Portrait` (styles with multiple pen roles: structure/midtone/bands), and confirm:
  - The pass list shows one row per **role**, not per pen-derived id (e.g. two "bands-*" passes with different pens collapse into one "bands" row with a single control, matching `apply_pass_overrides`'s all-or-nothing-per-role semantics — confirm this matches what a user would actually want, and flag it in review if not).
  - Changing a pen and re-rendering visibly changes that pass's ink color in the emulator preview.
  - Toggling visibility off + re-rendering removes that pass's ink entirely from the SVG export (open the downloaded SVG and confirm the layer is absent, not just hidden).
- **Done when**: a non-technical user can, from the Dev Panel alone, change which pen draws the "bands" pass and turn off the "hatch" pass on a portrait render, then export a print-ready SVG reflecting both changes.
