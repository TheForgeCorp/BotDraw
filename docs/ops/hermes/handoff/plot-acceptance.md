# Plot / job acceptance criteria

A job is **sellable / postable** when:
1. Status `ready` or `done` with no render error
2. `layers.json` pass_count ≥ 1 and pens match palette intent
3. Emulator preview reviewed (or stub plot-worker complete for path test)
4. Export pack present (`settings`, `layers`, `palette`, `motion_plan`, `stats`)
5. ETA / paper size match the SKU promise
6. No IP flags on source image/quote

**Reject / re-render** if:
- Empty passes, absurd stroke explosion vs quality preset
- Wrong palette, clipped content, unreadable letterforms
- Customer photo consent missing for public post
