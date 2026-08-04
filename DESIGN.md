---
name: BotDraw
description: Sophisticated minimal technical system for Dev Panel and venue-facing surfaces. Operate-mode tools; Persuade-mode venue later. Cool zinc neutrals, one ink accent, hairline structure, sans + mono only.
mode_default: Operate
colors:
  bg: "#fafafa"
  panel: "#ffffff"
  soft: "#f4f4f5"
  ink: "#0a0a0a"
  text: "#171717"
  muted: "#737373"
  faint: "#a3a3a3"
  line: "#e5e5e5"
  line-strong: "#d4d4d8"
  accent: "#0a0a0a"
  accent-hover: "#262626"
  focus: "#3b82f6"
  success: "#166534"
  warning: "#92400e"
typography:
  ui: "DM Sans, Helvetica Neue, Arial, sans-serif"
  mono: "JetBrains Mono, IBM Plex Mono, ui-monospace, monospace"
  # No display serif on product/tool surfaces. Venue may add a single editorial face later if briefed.
  scale:
    meta: "0.6875rem"   # 11
    label: "0.75rem"    # 12
    ui: "0.8125rem"     # 13
    body: "0.875rem"    # 14
    title: "1rem"       # 16
    panel: "1.125rem"   # 18
spacing:
  unit: "4px"
  panel-pad: "16px"
  rail-gap: "8px"
radius:
  control: "4px"
  panel: "6px"
  # Avoid rounded-full on primary CTAs and large containers.
borders:
  default: "1px solid #e5e5e5"
shadows: "none by default; optional 0 1px 0 rgba(0,0,0,0.04)"
motion:
  duration: "160ms"
  ease: "cubic-bezier(0.16, 1, 0.3, 1)"
  # State feedback only. No page-load choreography.
dials:
  DESIGN_VARIANCE: 4
  MOTION_INTENSITY: 2
  VISUAL_DENSITY: 5
skills:
  - .cursor/skills/impeccable
  - .cursor/skills/design-taste-frontend
  - .cursor/skills/minimalist-ui
  - .cursor/skills/redesign-existing-projects
  - .cursor/skills/high-end-visual-design
surfaces:
  letters_dev_panel:
    mode: Operate
    goal: Vectorize letter content and download plot-ready SVG / motion for hardware.
  venue_facing:
    mode: Persuade
    note: Same token world; more air, stronger brand lockup, paper preview as hero. Use impeccable + taste-skill when building.
anti_patterns:
  - Warm cream / terracotta / purple-indigo AI gradients
  - Nested cards, heavy shadows, glassmorphism as decoration
  - Serif display on tool chrome
  - Pill CTAs for primary actions
  - Emoji as UI
---

# BotDraw design system

**Reading:** Operate-mode technical product UI for plotter operators and venue staff; sophisticated minimal (Linear / Vercel adjacency), not craft-atelier and not dashboard-slop.

## Principles

1. **The tool disappears into the task.** Hierarchy via type weight, space, and hairlines — not color blocks.
2. **One accent:** near-black ink. Color appears only for state (focus, success, warning) or plot pen swatches.
3. **Sans + mono.** UI in DM Sans; measurements, timings, job IDs in JetBrains Mono.
4. **Flat structure.** Panels are bordered surfaces, not elevated cards. No nested cards.
5. **Skills authority.** Impeccable (Operate / quieter / distill / typeset / craft-floor) and Taste Skill (anti-slop, dials, redesign) govern Dev Panel and future venue-facing work.

## Letters Dev Panel IA

| Region | Role |
|--------|------|
| Top app tabs | BotDraw apps |
| LETTERS identity | Static product lockup |
| Left | Type rail + editor (layers, draft meta, palette, Vectorize) |
| Right | Paper emulator + margins + hardware download |

## Venue-facing (future)

Reuse these tokens. Shift dials toward `VARIANCE 5 / MOTION 3 / DENSITY 3`, keep the same neutrals and type, let the paper stage lead the first viewport.
