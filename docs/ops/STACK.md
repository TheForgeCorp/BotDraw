# Agent Stack Notes (Hermes vs OpenClaw)

**Decision status:** not locked. Governance in this folder is stack-agnostic.

## Recommendation for BotDraw mini-PC

Prefer **Hermes Agent** (Nous Research) as the default long-running operator when you are ready to pick:

- Persistent learning loop → booth FAQs and booking skills compound over time  
- Cron / scheduled digests fit morning–evening ops loops  
- Comfortable as a single always-on process beside BotDraw (`botdraw serve`)  
- Migration path exists if you start on OpenClaw (`hermes claw migrate`)

Choose **OpenClaw** first if your near-term pain is **multi-channel inbox** (WhatsApp/IG/Telegram gateway) and you want human-authored skills from ClawHub before self-learning.

Either way: load [OPERATOR_CHARTER.md](./OPERATOR_CHARTER.md) as soul/system context on every session.

## Mini-PC layout (suggested)

```text
mini-PC
  ├─ botdraw serve          # product API + Dev Lab
  ├─ hermes | openclaw      # operator agent daemon
  ├─ calendar + secrets     # agent-accessible, least privilege
  └─ docs/ops (this pack)   # cloned with the repo or synced
```

## Security minimums (both stacks)

- Separate credentials for: social draft tools, calendar, BotDraw API, Nav notify channel  
- No production payment secret in the agent tool list for v1  
- Publish actions disabled or gated behind a human approval tool  
- Log tool calls for bookings and outbound customer messages  
- Sandbox shell if the agent can run commands; BotDraw deploy stays Nav/engineering owned  

## When to lock the choice

Lock in `STACK.md` (this file) after a 1–2 week bakeoff on the mini-PC measuring:

1. Booking completion rate without Nav  
2. Draft quality (Nav edit distance)  
3. False escalations / missed escalations  
4. Uptime beside `botdraw serve`  
