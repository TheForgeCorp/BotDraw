---
name: venue-plotter-node
description: >
  Coordinate remote venue plot-worker over Tailscale using stub/emulator until hardware exists. Use for booth E2E tests and later AxiDraw.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Venue Plotter Node

## Model
Home brain stays up. Venue runs:
```bash
export BOTDRAW_API=http://<home-tailscale>:8080
botdraw plot-worker --driver stub
```

## APIs
queue → claim → motion → complete/fail

## Docs
`docs/host/PLOTTER_NODE.md`
