---
name: BotDraw
description: Apple-Operate Dev Lab — system gray desk, elevated paper sheet, compact rail. Operate-mode tools; Persuade-mode venue later.
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
  sheet: "2px"
borders:
  default: "1px solid #d2d2d7"
shadows:
  paper: "0 12px 40px rgba(29,29,31,0.12), 0 2px 6px rgba(29,29,31,0.06)"
  seg: "0 1px 2px rgba(29,29,31,0.08)"
motion:
  duration: "160ms"
  ease: "cubic-bezier(0.16, 1, 0.3, 1)"
dials:
  DESIGN_VARIANCE: 5
  MOTION_INTENSITY: 3
  VISUAL_DENSITY_RAIL: 6
  VISUAL_DENSITY_STAGE: 3
skills:
  - .cursor/skills/impeccable
  - .cursor/skills/design-taste-frontend
surfaces:
  dev_lab:
    mode: Operate
    goal: Compact controls + large paper-on-desk emulator across all apps.
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
---

# BotDraw design system

**Reading:** Operate Dev Lab for plotter operators — Apple / macOS canvas language (Final Cut inspector + Preview paper + Photos compact chrome). Not craft-atelier, not Linear-zinc dual theme.

## Principles

1. **Paper is the product.** The desk stage is the hero; the rail is a compact inspector.
2. **One chrome.** Tab switches change rail content and stage mode only.
3. **Restrained color.** Near-black ink accent; focus blue for state; pen swatches for plot color.
4. **System type.** SF / system UI stack; mono only for mm, ETA, job IDs.
5. **State motion only.** 160ms ease-out; no page-load choreography.

## Dev Lab IA

| Region | Role |
|--------|------|
| Top | Segmented app tabs |
| Left rail (~300px) | App controls; GenArt also hosts Layers/JSON/Job |
| Stage | Desk + elevated paper sheet + thin zoom/transport/Export… |

Portrait stage segments: **Source | Ingest | Vector** (one large view; default Vector).

## Paper stage

- Desk fill `#f5f5f7`
- Idle sheet fill `#ffffff`; after render uses Paper Library `paper_color_hex` (cream stocks are product color, not theme chrome)
- True paper aspect, contact shadow
- Shared HiDPI `EmulatorPlayer` (zoom, pan, loupe)
- Write-optimized canvas context (`willReadFrequently: false`)

## Responsive

- Desktop: `300px` rail + flex stage, full viewport height
- `≤900px`: rail stacks above stage (~34vh); stage toolbar sticky at bottom for zoom/play/export

## States

| State | Behavior |
|-------|----------|
| Empty | White sheet on desk; stats “Ready”; Export actions disabled |
| Loading | Stats line shows busy copy (Ingesting… / Vectorizing…) |
| Ready | Sheet shows ink; Export… enabled for current app |
| Error | Stats line shows message; controls remain usable |

## Finish review (apple-devlab-shell-5528)

Disposition: **pass with notes** (2026-08-04). Material fixes landed: style-grid name-only labels, idle white sheet, sticky mobile toolbar. Seeded demo ink on every tab left as follow-up.
