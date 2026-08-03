---
name: order-fulfill
description: >
  Turn Etsy/web orders into BotDraw renders and digital/physical fulfillment. Queue plot-worker jobs for venue. Use on new paid orders.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Order → Fulfill

## Digital
1. Map SKU → style/palette/settings
2. `botdraw` render / API render
3. Attach export pack / SVG to delivery
4. Mark fulfilled

## Physical / booth plot
1. Leave job `ready` on home API
2. Venue `plot-worker` claims over Tailscale
3. Complete/fail via plot APIs

## Unique art
Lock status `plotting` so two nodes cannot claim the same job.
