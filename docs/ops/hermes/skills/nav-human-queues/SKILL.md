---
name: nav-human-queues
description: >
  Maintain and present Nav’s three action queues: date confirm, cash collect, phone needed. Use in every digest and when any gate triggers.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Nav Human Queues

## Queues
1. DATE CONFIRM
2. CASH TO COLLECT
3. PHONE NEEDED

## On Nav reply
- Date confirm → move booking to confirmed + send customer template
- Cash ack → mark invoice paid
- Phone done → clear phone item with notes
