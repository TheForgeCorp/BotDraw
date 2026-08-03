# Hardware — BotDraw mini-PC

**Role:** one portable always-on Ubuntu box (home or venue).  
**LLM:** local **Ollama** up front + Hermes primary brain on **Claude Max**.

## Minimum (local AI included)

| | Spec |
|---|---|
| CPU | 6+ cores preferred (Intel N100+/N305, Ryzen 5, or better) |
| RAM | **32 GB** (16 GB only if you stick to ≤3B–7B models and accept swap risk) |
| Storage | **512 GB SSD** minimum (1 TB recommended for jobs + models) |
| GPU | Optional; speeds larger local models. Not required for Claude Max or small Ollama models |
| Network | Ethernet or solid Wi‑Fi; phone hotspot OK at venues |
| OS | **Ubuntu 24.04 LTS** (22.04 OK) |
| Power | AC 24/7; expect ~15–40 W with Ollama idle/light load |

## Recommended buy target

- 8 cores · **32 GB RAM** · **1 TB NVMe** · Ubuntu-friendly mini-PC  
- Leave headroom for: Hermes, BotDraw, Ollama (`llama3.1:8b` class), website tooling, job artifacts  

## Model sizing (Ollama, rough)

| RAM free for models | Reasonable default |
|---|---|
| ~8–12 GB | `llama3.2:3b` (BotDraw LettersBot default) |
| ~16–20 GB | `llama3.1:8b` or `qwen2.5:7b` (better letters / Hermes fallback) |
| 24 GB+ VRAM/unified | 14B–32B class if you upgrade later |

Bootstrap pulls `llama3.2:3b` always and `llama3.1:8b` when ≥28 GB RAM is detected.

## Venue / remote plotter node

Keep the **home mini-PC plugged in** (Hermes uninterrupted). E2E test on **any remote PC** over Tailscale with no plotter:

```bash
export BOTDRAW_API=http://botdraw-home:8080
botdraw plot-worker --driver stub
```

Later at booths: same worker with `--driver axidraw`. Details: [../host/PLOTTER_NODE.md](../host/PLOTTER_NODE.md).
