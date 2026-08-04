---
name: BotDraw
description: Apple-Operate Dev Lab — system gray desk, elevated paper sheet, Settings-style rail groups, floating craft-bar toolbar. Operate-mode tools; Persuade-mode venue later.
mode_default: Operate
colors:
  desk: "#f5f5f7"
  bg: "#f5f5f7"
  panel: "#ffffff"
  soft: "#f0f0f2"
  ink: "#1d1d1f"
  text: "#1d1d1f"
  muted: "#6e6e73"
  faint: "#86868b"
  line: "#d2d2d7"
  line-strong: "#c7c7cc"
  accent: "#1d1d1f"
  accent-hover: "#424245"
  focus: "#0071e3"
  success: "#248a3d"
  warning: "#b25000"
typography:
  ui: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
  mono: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
  scale:
    meta: "0.6875rem"
    label: "0.75rem"
    ui: "0.8125rem"
    body: "0.875rem"
    title: "0.9375rem"
spacing:
  unit: "4px"
  panel-pad: "12px"
  rail-gap: "8px"
  rail-width: "300px"
radius:
  control: "6px"
  panel: "8px"
  group: "10px"
  sheet: "2px"
  craft-bar: "999px"
borders:
  default: "1px solid #d2d2d7"
shadows:
  paper: "0 18px 48px rgba(29,29,31,0.16), 0 4px 12px rgba(29,29,31,0.08), 0 1px 0 rgba(255,255,255,0.65) inset"
  seg: "0 1px 2px rgba(29,29,31,0.08)"
  craft-bar: "0 8px 28px rgba(29,29,31,0.12)"
motion:
  duration: "160ms"
  press: "100ms scale(0.97)"
  sheet-swap: "280–320ms opacity + soft scale (critically damped; no bounce)"
  ease: "cubic-bezier(0.16, 1, 0.3, 1)"
  reduced-motion: "cross-fade only; no press scale / sheet scale"
dials:
  DESIGN_VARIANCE: 5
  MOTION_INTENSITY: 3
  VISUAL_DENSITY_RAIL: 5
  VISUAL_DENSITY_STAGE: 3
skills:
  - .cursor/skills/impeccable
  - .cursor/skills/design-taste-frontend
  - .cursor/skills/apple-design
surfaces:
  dev_lab:
    mode: Operate
    goal: Compact grouped controls + large paper-on-desk emulator across all apps.
  venue_facing:
    mode: Persuade
    note: Same tokens; more air; paper preview as hero.
anti_patterns:
  - Warm cream / terracotta craft theme
  - Dual shell layouts per app
  - Serif tool chrome
  - Pill CTA clusters / six equal export buttons
  - Nested cards / decorative glass
  - Permanent Source|Ingest|Vector strip stealing paper space
  - Equal-weight bordered button soup in the rail
  - Black filled mode tiles mixed with outline grids
---

# BotDraw design system

**Reading:** Operate Dev Lab for plotter operators — Apple / macOS canvas language (Final Cut inspector + Preview paper + Photos compact chrome). Not craft-atelier, not Linear-zinc dual theme.

## Principles

1. **Paper is the product.** The desk stage is the hero; the rail is a compact inspector.
2. **One chrome.** Tab switches change rail content and stage mode only.
3. **Restrained color.** Near-black ink accent; focus blue for state; pen swatches for plot color.
4. **System type.** SF / system UI stack; mono only for mm, ETA, job IDs. Rail titles weight 600 / tracking −0.02em.
5. **State motion only.** Press scale on pointer-down (~100ms); sheet swaps opacity+soft scale; no page-load choreography.
6. **Settings grammar.** Rail blocks live in inset `.group` wells (`#f0f0f2` + white rows); primary CTA sits outside the group.
7. **Progressive disclosure.** Common path first; Scan / Ensemble / AI / draft meta under Advanced.

## Dev Lab IA

| Region | Role |
|--------|------|
| Top | Segmented app tabs (translucent material chrome) |
| Left rail (~300px) | Grouped controls + Advanced; GenArt also hosts Layers/JSON/Job |
| Stage | Desk + elevated paper + floating craft-bar (zoom / transport / Export…) |

Portrait stage segments: **Source | Ingest | Vector** (one large view; default Vector).

## Materials

- **Desk:** soft vignette + faint grain over `#f5f5f7` → `#ececf0` (table plane, not flat fill)
- **Sheet:** white idle; Paper Library cream only after render; strong contact shadow + bright top edge
- **Craft bar:** translucent capsule over desk bottom (`backdrop-filter`); solid white when `prefers-reduced-transparency`
- **Top bar:** frosted white; same reduced-transparency solid fallback

## Paper stage

- Idle sheet fill `#ffffff`; after render uses Paper Library `paper_color_hex`
- True paper aspect, contact shadow
- Shared HiDPI `EmulatorPlayer` (zoom, pan with rubber-band + velocity settle, loupe)
- Write-optimized canvas context (`willReadFrequently: false`)
- Empty cue centered on desk (“Drop a photo or Vectorize”); loading = stats + subtle sheet shimmer

## Responsive

- Desktop: `300px` rail + flex stage, full viewport height
- `≤900px`: rail stacks above stage (~34vh); craft bar remains floating at stage bottom

## States

| State | Behavior |
|-------|----------|
| Empty | White sheet + mute empty cue; Export actions disabled |
| Loading | Stats busy copy + `is-loading` sheet shimmer |
| Ready | Sheet shows ink; Export… enabled for current app |
| Error | Stats line shows message under failed action path; controls remain usable |

## A11y

- `prefers-reduced-motion: reduce` — no press scale / sheet scale; sheet swaps cross-fade
- `prefers-reduced-transparency: reduce` — solid top bar + craft bar

## Finish review (apple-design materials pass)

Disposition: **pass with notes** against emilkowalski/apple-design (2026-08-04). Materials, grouped rail, press response, craft-bar toolbar, reduced-motion/transparency, and progressive Advanced disclosures landed. Emulator rubber-band + velocity settle added. Ingest/vectorization quality remains frozen pending UI sign-off.
