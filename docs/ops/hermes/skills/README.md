# Hermes starter skills (BotDraw)

**Stack locked:** Hermes + Claude Max (primary) + Ollama (local).

Install/copy this folder into Hermes skills path on the mini-PC (see Hermes docs for `skills/` location), or symlink:

```bash
ln -s /opt/botdraw/docs/ops/hermes/skills ~/.hermes/skills/botdraw
# exact path may vary by Hermes version — adjust after `hermes` install
```

Ask Hermes on first boot: *Review all BotDraw skills under docs/ops/hermes/skills, load botdraw-orientation, and propose an enablement order.*

## Skill index

| Skill | Purpose |
|---|---|
| `botdraw-orientation` | Load first on new sessions |
| `daily-ops-digest` | Compose and send Nav the daily ops digest: sales, holds awaiting date confirm, cash-to-col |
| `booking-holds` | Qualify session leads, propose 1-3 slots, place calendar holds (hold_pending_nav) |
| `customer-support` | Answer customer FAQs on email/WhatsApp/Telegram/IG/Etsy with approved scripts |
| `lead-followups` | Follow up cold leads and no-shows asynchronously |
| `instagram-ops` | Publish Instagram posts/stories/reels from BotDraw outputs and brand calendar; reply to DM |
| `website-ops` | Maintain BotDraw website content, intake forms, booking CTA, uptime, and basic SEO |
| `etsy-multi-shop` | Operate one or many Etsy shops: listings, messages, orders, policy refunds, reviews |
| `order-fulfill` | Turn Etsy/web orders into BotDraw renders and digital/physical fulfillment |
| `content-from-jobs` | After successful BotDraw jobs, draft and schedule IG/site gallery content |
| `ab-listings` | A/B test Instagram captions and Etsy titles/tags; keep winners |
| `pricing-bands` | Adjust listing/session prices only inside Nav-approved bands in approvals/pricing |
| `inventory-stock` | Watch stock/low inventory; pause or unpause Etsy/site listings |
| `multi-shop-syndication` | Syndicate one BotDraw artwork into niche variants across Etsy shops with unique copy/tags |
| `shipping-tracking` | Create shipping labels and post tracking where APIs allow |
| `policy-refunds` | Issue refunds/cancellations strictly inside each shop’s published policy |
| `ad-boosts` | Run Meta/IG boosts within monthly budget cap |
| `competitor-research` | Research competitor listings and trends; produce reports without copying IP or trademarks |
| `website-seo` | Fix website SEO: titles, meta, FAQs, internal links, broken links |
| `mini-pc-sre` | Monitor and heal mini-PC services: botdraw, ollama, disk, restarts, logs |
| `botdraw-job-qa` | QA BotDraw jobs: failed renders, retry, flag bad styles, inspect layers/export packs |
| `venue-plotter-node` | Coordinate remote venue plot-worker over Tailscale using stub/emulator until hardware exis |
| `backups` | Back up jobs/exports/config to Nav-designated storage |
| `expense-logging` | Log expenses and receipts for Nav |
| `tax-exports` | Draft tax/sales export packs for the accountant |
| `restock-lists` | Maintain pens/paper/shipping supply shopping lists for Nav to purchase |
| `event-outreach` | Draft and send async booth/event outreach emails |
| `collab-drafts` | Draft influencer/collab negotiations |
| `red-team-governance` | Run adversarial self-tests: angry buyer, double-book, IP trap, cash/phone bypass attempts |
| `autonomy-scoreboard` | Publish weekly autonomy metrics: human minutes/day, confirm latency, errors, unattended re |
| `skill-writeback` | Weekly: write improved procedures into docs/ops/memory and propose skill patches |
| `personal-assistant` | Optional Nav personal calendar/reminders on the same box |
| `ollama-babysitting` | Keep local Ollama healthy for LettersBot and Hermes fallback |
| `nav-human-queues` | Maintain and present Nav’s three action queues: date confirm, cash collect, phone needed |

## Review checklist for Hermes

1. Read `botdraw-orientation`
2. Confirm human gates still match `GOVERNANCE.md`
3. Enable P0 skills first: `mini-pc-sre`, `daily-ops-digest`, `nav-human-queues`, `booking-holds`, `customer-support`
4. Then commerce: `etsy-multi-shop`, `instagram-ops`, `website-ops`, `order-fulfill`
5. Mark live/planned in `docs/ops/memory/capability-status.md`

