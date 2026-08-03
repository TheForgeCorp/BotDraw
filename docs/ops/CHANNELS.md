# Channels — Website, Instagram, Etsy

## Website

**Owner:** operator agent  
**Duties:** uptime, content, intake forms, booking request flow, basic SEO, SSL/domain alerts (escalate DNS account issues to Nav).  
**Booking:** site should create `hold_proposed` records — never show “confirmed” until Nav date-confirm.  
**Cash:** if a page mentions cash-pay booths, state that cash is collected in person by the human operator.

## Instagram

**Owner:** operator agent  
**Duties:** content calendar, publish, hashtags within brand voice, reply DMs/comments, hide spam, escalate harassment (P0).  
**SLA:** public comments ≤ 4h during booth hours; DMs ≤ 2h.  
**Media:** prefer BotDraw outputs / consented customer work / owned photos. No scraped celebrity images.  
**Phone:** never ask users to “call us”; offer form, DM, or email.

## Etsy — multi-shop

Each shop is an isolated commercial surface.

```text
docs/ops/approvals/shops/<shop-id>.md
  - shop_id, etsy_shop_name, niche, brand_voice pointer
  - sku_prefix, shipping profiles, refund policy pointer
  - fulfillment: digital_download | plot_then_ship | session_upsell
```

**Owner:** operator agent for all listed shops  
**Duties per shop:** listings, SEO titles/tags, messages, order pipeline, policy refunds, reviews reply  
**Cross-shop rules:**

- Unique physical plots: lock inventory globally when sold in any shop  
- Do not reuse the same listing copy verbatim across shops if niches differ  
- Separate message templates per shop voice  

**New shop:** ask Nav before creating or connecting credentials.

## Customer reply principles (all channels)

1. Async only (no phone)  
2. Propose booking dates; say “we’ll confirm the time shortly” until Nav confirms  
3. For cash-pay: “Cash is collected in person — we’ll confirm when received”  
4. Platform checkout preferred for remote sales  
5. Log order/booking ids in replies when helpful  

## Outage playbook (short)

1. Detect (healthcheck fail)  
2. Restart service once  
3. If still down: status note on IG story/site banner if customer-facing  
4. P0 escalate to Nav with impact on open orders/sessions  
