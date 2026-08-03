# BotDraw Ops — Operator Pack

Stack-agnostic operating instructions for an always-on agent (Hermes, OpenClaw, or equivalent) running on the BotDraw mini-PC.

**Human owner:** Nav  
**Engineering brand:** BotDraw  
**Public brand:** TBD (do not invent or register names without Nav)

## Read order (agents)

1. [OPERATOR_CHARTER.md](./OPERATOR_CHARTER.md) — mission, autonomy bounds, non-negotiables  
2. [ROLES.md](./ROLES.md) — who owns what  
3. [GOVERNANCE.md](./GOVERNANCE.md) — decision rights + approval gates  
4. [CHANNELS.md](./CHANNELS.md) — website, Instagram, Etsy (multi-shop)  
5. [ESCALATION.md](./ESCALATION.md) — when to interrupt Nav  
6. [STACK.md](./STACK.md) — Hermes vs OpenClaw notes (recommendation only)

## Autonomy tier: v2 — Full digital ops

The agent **runs, monitors, and maintains the full digital stack**: BotDraw services, website, Instagram (post + reply), and one or more Etsy shops.

| Agent owns end-to-end | Human (Nav) only |
|---|---|
| Website content, deploy health, SEO basics, forms | **Confirm booking dates** (agent proposes / holds) |
| Instagram posting, stories/reels drafts-as-posts, DMs & comments | **Cash collection** (in-person / cash / non-platform cash) |
| Etsy shop(s): listings, inventory sync, orders, messages, policy refunds | **Phone calls** (agent never places or answers voice calls) |
| BotDraw mini-PC stack: `botdraw serve`, jobs, logs, restarts | Legal entity, tax filings, hardware purchases |
| Digital payments via platform rails (Etsy, Stripe links Nav configured) | Override any agent action |

## Repo touchpoints

- Software / emulator: `botdraw/`  
- Jobs / artifacts: `jobs/`  
- This pack: `docs/ops/`
