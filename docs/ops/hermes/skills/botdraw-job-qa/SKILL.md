---
name: botdraw-job-qa
description: >
  QA BotDraw jobs: failed renders, retry, flag bad styles, inspect layers/export packs. Use when jobs fail or quality complaints arrive.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# BotDraw Job QA

## Tools
- Dev Lab / API `/api/jobs/{id}`
- layers.json / export_pack.json
- Re-render with new seed/quality

## Escalate
Repeated style failures → engineering note in digest
