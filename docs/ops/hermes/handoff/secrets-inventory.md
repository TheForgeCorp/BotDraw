# Secrets inventory (names only — never commit values)

| Account | Purpose | Ink access? | 2FA owner |
|---|---|---|---|
| Anthropic / Claude Max | Hermes primary LLM | via Hermes auth | Nav |
| Telegram bot / user | Ops + customer async | yes | Nav |
| Instagram | Publish/reply | yes | Nav |
| Etsy shop(s) | Listings/orders | yes | Nav |
| Domain / DNS | Website | limited | Nav |
| Hosting / CMS | Website | yes | Nav |
| Tailscale | Home↔venue | yes | Nav |
| Ollama | local | local only | n/a |
| Shipping API | labels | optional | Nav |
| Ads (Meta) | boosts ≤ cap | yes | Nav |
| Bank / payouts | money | **no** | Nav |

Store secrets in Hermes auth / OS keyring / `/etc/botdraw/` — **not** in git.
