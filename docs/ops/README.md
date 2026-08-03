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
5. [CAPABILITIES.md](./CAPABILITIES.md) — Nav-approved automation surface (1–28, all yes)  
6. [HARDWARE.md](./HARDWARE.md) — mini-PC specs (local AI up front)  
7. [ESCALATION.md](./ESCALATION.md) — when to interrupt Nav  
8. [STACK.md](./STACK.md) — Hermes + Claude Max + Ollama  
9. Host bootstrap: [`../host/README.md`](../host/README.md)

## Autonomy tier: v2 — Full digital ops

The agent **runs, monitors, and maintains the full digital stack**: BotDraw services, website, Instagram (post + reply), and one or more Etsy shops.

**LLM:** Hermes via Nav’s **Claude Max** account; **Ollama local AI installed up front** on the same mini-PC (LettersBot + Hermes fallback).

**Expanded surface:** all items in [CAPABILITIES.md](./CAPABILITIES.md) (1–28) are approved.

**Host install:** [`../host/UBUNTU_MINIPC.md`](../host/UBUNTU_MINIPC.md) · [`../../scripts/bootstrap_minipc.sh`](../../scripts/bootstrap_minipc.sh)

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
