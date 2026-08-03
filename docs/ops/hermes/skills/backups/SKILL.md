---
name: backups
description: >
  Back up jobs/exports/config to Nav-designated storage. Use on nightly cron or before risky upgrades.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Backups

## Include
- `jobs/` artifacts+records
- `/etc/botdraw/` (no leaking secrets to public git)
- ops memory notes

## Verify
Restore test periodically; report in weekly digest
