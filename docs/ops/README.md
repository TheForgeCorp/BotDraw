# BotDraw Ops — Operator Pack

Stack-agnostic operating instructions for an always-on agent (Hermes, OpenClaw, or equivalent) running on the BotDraw mini-PC.

**Human owner:** Nav  
**Engineering brand:** BotDraw  
**Public brand:** TBD (do not invent or register names without Nav)

## Read order (agents)

1. [OPERATOR_CHARTER.md](./OPERATOR_CHARTER.md) — mission, autonomy bounds, non-negotiables  
2. [ROLES.md](./ROLES.md) — who owns what  
3. [GOVERNANCE.md](./GOVERNANCE.md) — decision rights + approval gates  
4. [ESCALATION.md](./ESCALATION.md) — when to interrupt Nav  
5. [STACK.md](./STACK.md) — Hermes vs OpenClaw notes (recommendation only)

## v1 autonomy (locked)

| Agent may do alone | Needs Nav approval |
|---|---|
| Draft website / IG / email copy | Publish or schedule public posts |
| Answer FAQs from approved scripts | Change pricing, offers, or brand voice |
| Create calendar **holds** and **confirmed bookings** within capacity rules | Refunds, discounts > policy, custom contracts |
| Send booking confirmations / reminders (templated) | Payments, payouts, tax, legal |
| Ops digests + plotter/job health summaries | Hardware purchase, live booth exceptions |
| Lead capture + CRM notes | Likeness / lyric / IP edge cases |

## Repo touchpoints

- Software / emulator: `botdraw/`  
- Jobs / artifacts: `jobs/`  
- This pack: `docs/ops/`
