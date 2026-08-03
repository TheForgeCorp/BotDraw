---
name: daily-ops-digest
description: >
  Compose and send Nav the daily ops digest: sales, holds awaiting date confirm, cash-to-collect, phone-needed, outages, open risks. Use each morning/evening or when asked for status.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Daily Ops Digest

## Cadence
- Morning + evening (or cron)

## Always include
```text
DATE CONFIRM: booking_id · customer · proposed slots · hold expiry
CASH TO COLLECT: invoice_id · amount · when/where
PHONE NEEDED: why · customer · callback window
SALES: orders / revenue (platform)
STACK: botdraw · ollama · site · IG · etsy health
RISKS: P0/P1 open
```

## Rules
- Async only (Telegram/Slack/SMS — never call)
- Link job/order ids when available
- Keep under ~40 lines unless P0
