# Agent Stack Notes

**Decision status:** Hermes selected · LLM = Nav Claude Max account  

OpenClaw remains a possible alternate gateway later; governance stays readable by either.

## Recommendation for BotDraw mini-PC

**Hermes Agent** + Claude Max is the locked starting stack:

- Persistent learning loop → booth FAQs and booking skills compound over time  
- Cron / scheduled digests fit morning–evening ops loops  
- Comfortable as a single always-on process beside BotDraw (`botdraw serve`)  
- Auth: `hermes model` → Anthropic / Claude Max path (API key or OAuth per Hermes docs)  

Either way: load [OPERATOR_CHARTER.md](./OPERATOR_CHARTER.md) as soul/system context on every session. Also load [CAPABILITIES.md](./CAPABILITIES.md). Grant tools for website CMS, Instagram publish/reply, Etsy multi-shop, calendar holds, support inboxes, and BotDraw health — **deny** dialer/VoIP and any “mark cash paid” tool that bypasses Nav ack.

## Mini-PC layout (suggested)

```text
mini-PC
  ├─ botdraw serve              # product API + Dev Lab
  ├─ hermes | openclaw          # operator agent daemon
  ├─ website (CMS/static host)  # agent-managed
  ├─ IG + Etsy credentials      # least privilege per shop
  ├─ calendar                   # holds; Nav confirms dates
  └─ docs/ops (this pack)       # cloned/synced with repo
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
