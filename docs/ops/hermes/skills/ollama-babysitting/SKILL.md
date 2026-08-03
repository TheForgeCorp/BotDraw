---
name: ollama-babysitting
description: >
  Keep local Ollama healthy for LettersBot and Hermes fallback. Pull/update models carefully. Use on LLM failures or host bootstrap follow-up.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Ollama Babysitting

## Health
```bash
systemctl status ollama
ollama list
curl -sf http://127.0.0.1:11434/api/tags
```

## Models
Default `llama3.2:3b`; `llama3.1:8b` if RAM ≥ 28GB (`docs/ops/HARDWARE.md`)

## LettersBot
Respect `BOTDRAW_OLLAMA_MODEL` / `OLLAMA_HOST` in `/etc/botdraw/botdraw.env`
