---
name: mini-pc-sre
description: >
  Monitor and heal mini-PC services: botdraw, ollama, disk, restarts, logs. Use on alerts, cron health, or degraded mode.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Mini-PC SRE

## Checks
```bash
systemctl is-active botdraw ollama
curl -sf http://127.0.0.1:8080/api/health
curl -sf http://127.0.0.1:11434/api/tags
df -h /
```

## Actions
- Restart once on failure
- Customer-facing status note if needed
- P0 if down during active orders/sessions

## Don’t
Unplug/migrate Hermes home brain for venue plotting — use plot-worker.
