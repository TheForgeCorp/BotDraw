---
name: etsy-multi-shop
description: >
  Operate one or many Etsy shops: listings, messages, orders, policy refunds, reviews. Keep shops isolated. Use whenever Etsy work appears.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Etsy Multi-Shop

## Per shop
Playbook: `docs/ops/approvals/shops/<shop-id>.md`

## Rules
- No cross-shop inventory double-sell of unique plots
- Distinct voice/copy per niche
- Refunds only inside published policy; else escalate P1

## New shop
Ask Nav before creating/connecting credentials.
