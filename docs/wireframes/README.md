# Wireframes & mockups

| File | Purpose |
|------|---------|
| [portraitbot-phase-b.html](portraitbot-phase-b.html) | Low-fi wireframe plan |
| [portraitbot-phase-b-mockup.html](portraitbot-phase-b-mockup.html) | DESIGN.md Operate mockup (interactive stages, gate, channels) |
| [portraitbot-phase-b-gold.html](portraitbot-phase-b-gold.html) | Classic gold-gate review (+ optional vision fixtures section) |
| [portraitbot-vision-loop-history.html](portraitbot-vision-loop-history.html) | 3-turn AI vision loop visual history (scene → structure → confirm) |

## Review links (remote)

**Vision loop history (3 turns):**  
https://htmlpreview.github.io/?https://github.com/TheForgeCorp/BotDraw/blob/cursor/portraitbot-phase-b-wireframe-b124/docs/wireframes/portraitbot-vision-loop-history.html

**Classic gold-gate report (with vision fixtures):**  
https://htmlpreview.github.io/?https://github.com/TheForgeCorp/BotDraw/blob/cursor/portraitbot-phase-b-wireframe-b124/docs/wireframes/portraitbot-phase-b-gold.html

**Mockup:**  
https://htmlpreview.github.io/?https://github.com/TheForgeCorp/BotDraw/blob/cursor/portraitbot-phase-b-wireframe-b124/docs/wireframes/portraitbot-phase-b-mockup.html

**Wireframe plan:**  
https://htmlpreview.github.io/?https://github.com/TheForgeCorp/BotDraw/blob/cursor/portraitbot-phase-b-wireframe-b124/docs/wireframes/portraitbot-phase-b.html

Open local HTML in a browser (self-contained).

```bash
botdraw gold report --with-vision-fixtures   # classic gate + 3-turn summaries
botdraw vision loop-demo                     # full pass-by-pass structure previews
```

**Live Dev Lab:** PortraitBot Phase B chrome is wired in `botdraw/web/` — calculation window (structure / ShadeField / AI vision turns / assessment), gate checklist (Apply locked until all checks), defaults Ingest + classic + hatch off + underlay none. Studio Ingest runs turns 1–2; Vectorize carries state and runs turn 3 confirm.
