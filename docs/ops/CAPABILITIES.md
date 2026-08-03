# Approved Hermes capabilities (Nav: yes to all)

**Status:** approved experiment scope — 2026-08-03  
**Runtime:** Hermes + Claude Max (Nav account) on BotDraw mini-PC  
**Human gates (unchanged):** confirm booking dates · cash collection · phone calls  

Hermes may implement and operate every item below. Prioritize by ROI; do not block on building all at once.

## Commerce & channels

1. Daily ops digest to Nav’s phone (sales, holds awaiting date confirm, cash-to-collect, outages)  
2. Customer support inbox (email / WhatsApp / Telegram) with scripted FAQ replies  
3. Lead follow-ups and no-show reminders (async only)  
4. Review request + review reply on Etsy/Google  
5. Content calendar + auto-post from finished BotDraw jobs  
6. A/B test captions/listings; keep winners  
7. Price tweaks inside approved bands ([approvals/pricing.md](./approvals/pricing.md))  
8. Inventory / low-stock alerts; pause/unpause listings  
9. Multi-shop listing syndication (same art → niche variants)  
10. Order → BotDraw render → fulfill digital download pipeline  
11. Shipping label / tracking updates where APIs allow  
12. Refunds/cancellations inside published shop policy  
13. Ad boosts within monthly budget cap  
14. Competitor/listing research reports (no copying IP)  
15. SEO fixes on the website (titles, FAQs, broken links)  

## Stack & product

16. Mini-PC SRE: healthchecks, restarts, log triage, disk alerts  
17. BotDraw job QA (failed plots, retry, flag bad styles)  
18. Backup of jobs/exports/config to Nav-designated storage  
19. Expense/receipt logging (no autonomous spending)  
20. Tax/sales export packs for accountant (draft only)  
21. Vendor restock shopping lists (pens/paper) — Nav still buys  
22. Event/booth outreach emails — Nav takes calls  
23. Collab/influencer negotiation drafts that stop before a call  
24. Red-team self-tests (angry buyer, double-book, IP trap)  
25. Autonomy scoreboard (human minutes/day, confirm latency, errors)  
26. Weekly skill/process writeback into `docs/ops/memory/`  
27. Personal-assistant side tasks on the same box (calendar, reminders) — keep **separate** from BotDraw brand voice/channels  
28. Local LettersBot LLM babysitting (Ollama up/down) when enabled  

## Build order (suggested)

```text
P0  16, 1, 2, 3, booking holds + date-confirm queue
P1  5, 10, 8, 12, 15, website + IG + Etsy live loop
P2  6, 7, 9, 11, 13, 4, 17, 18
P3  14, 19–23, 24–26, 27–28
```

## Still forbidden

- Phone calls  
- Cash handling / marking cash paid without Nav ack  
- Confirming bookings without Nav date confirm  
- Spending outside ad budget / buying hardware  
- Expanding human gates without a git update to governance  

## Tracking

Log enablement in `docs/ops/memory/capability-status.md` (agent-maintained): `id · status(planned|building|live|paused) · notes`.
