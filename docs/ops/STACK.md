# Agent Stack Notes

**Decision status:** Hermes + Claude Max (primary) · **Ollama local AI up front** (LettersBot + Hermes fallback)  
**Host OS:** Ubuntu 22.04/24.04 mini-PC — see [`docs/host/`](../host/)

## Locked stack

| Layer | Choice |
|---|---|
| Operator agent | **Hermes Agent** |
| Primary LLM | Nav **Claude Max** (Anthropic via `hermes model`) |
| Local LLM | **Ollama** on the same mini-PC (`llama3.2:3b` min; `llama3.1:8b` if ≥28 GB RAM) |
| Product API | `botdraw serve` systemd unit |
| Bootstrap | [`scripts/bootstrap_minipc.sh`](../../scripts/bootstrap_minipc.sh) |

Load every session:

- [OPERATOR_CHARTER.md](./OPERATOR_CHARTER.md)  
- [CAPABILITIES.md](./CAPABILITIES.md)  
- [GOVERNANCE.md](./GOVERNANCE.md)  
- Starter skills: [hermes/skills/](./hermes/skills/)  

Grant tools for website, Instagram, Etsy, calendar holds, support inboxes, BotDraw health.  
**Deny** dialer/VoIP and any “mark cash paid” tool that bypasses Nav ack.

## Mini-PC layout

```text
HOME mini-PC (Ubuntu, 24/7)
  ├─ ollama.service
  ├─ botdraw.service             # control plane :8080
  ├─ hermes                      # Telegram ops
  └─ /opt/botdraw

VENUE plotter node (laptop / small PC)
  ├─ Tailscale → home API
  ├─ botdraw plot-worker         # claim → plot → complete
  └─ USB AxiDraw
```

See [PLOTTER_NODE.md](../host/PLOTTER_NODE.md).

## Security minimums

- Separate credentials for social, calendar, shops, Nav notify channel  
- Claude Max / Anthropic tokens only in Hermes auth store or root-restricted env — **never commit**  
- No production payment secret in loose agent tools  
- Log booking + outbound customer tool calls  
- Sandbox shell where Hermes allows it  

## Replication

New node = clone repo → `sudo ./scripts/bootstrap_minipc.sh` → `hermes model`.  
Details: [UBUNTU_MINIPC.md](../host/UBUNTU_MINIPC.md)
