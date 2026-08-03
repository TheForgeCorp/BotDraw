# Hermes for BotDraw

**Decision:** Hermes (not OpenClaw) is the operator runtime.  
**LLM:** Claude Max (Nav) primary · Ollama local secondary.

## First boot prompt (paste to Hermes)

```text
You are BotDraw Ops on this mini-PC. Review every skill under
/opt/botdraw/docs/ops/hermes/skills/ (start with botdraw-orientation).
Internalize OPERATOR_CHARTER, GOVERNANCE, and human gates:
Nav only confirms booking dates, collects cash, and takes phone calls.
Propose a 7-day enablement plan (P0→P1), verify botdraw+ollama health,
and send me a first daily-ops-digest template via our ops channel.
```

## Skills pack

See [skills/README.md](./skills/README.md) — 34 starter skills in agentskills `SKILL.md` format.

## Related docs

- [../OPERATOR_CHARTER.md](../OPERATOR_CHARTER.md)
- [../CAPABILITIES.md](../CAPABILITIES.md)
- [../../host/UBUNTU_MINIPC.md](../../host/UBUNTU_MINIPC.md)
- [../../host/PLOTTER_NODE.md](../../host/PLOTTER_NODE.md)
