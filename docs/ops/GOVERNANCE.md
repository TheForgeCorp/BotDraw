# Governance & Decision Rights

## Autonomy tier: v2 — Full digital ops

Frozen until Nav changes this section in git.

Human-required actions are **only**:

1. Confirm booking dates  
2. Collect cash  
3. Phone calls  

### Allow (agent executes)

**Stack / SRE**

- Run, monitor, restart BotDraw (`botdraw serve`), website, agent runtime  
- Rotate logs, verify disk, alert on failed jobs  
- Apply dependency updates that are routine and reversible; roll back on failure  

**Website**

- Edit and publish pages, blogs, FAQs, booking intake  
- Maintain SEO basics, broken-link checks, form deliverability  
- Deploy static/site updates via the approved deploy path  

**Instagram**

- Create, schedule, and **publish** posts/stories/reels within brand voice  
- Reply to DMs and comments; moderate obvious spam  
- Use customer work in feed **only** when consent flag is recorded  

**Etsy (one or many shops)**

- Create/update listings, photos, attributes, shipping profiles per shop playbook  
- Answer buyer messages; push production/plot queues for digital or physical SKUs  
- Issue refunds/cancellations **inside** each shop’s published policy  
- Sync inventory flags across shops without double-selling the same unique plot  

**Booking**

- Qualify leads, propose 1–3 slots, place calendar **holds** (`status=hold_pending_nav`)  
- After Nav confirms date → set `confirmed`, send templates, reminders  
- Cancel/reschedule holds that expire or that Nav rejects  

**Money (digital only)**

- Accept platform checkout (Etsy, Nav-configured payment links)  
- Record cash-due invoices for Nav; never mark cash paid without Nav ack  
- Stay inside price bands in `approvals/pricing.md`  

### Ask first (Nav)

- Confirm / pick final booking date-time  
- Any situation that requires a **phone call**  
- Cash received / cash refund in person  
- New Etsy shop open/close, new domain, or new payout account  
- Price band changes, new service SKUs outside catalog  
- Ad spend above the monthly budget cap in `approvals/pricing.md`  
- Hardware / supply purchases  
- Off-policy refunds, legal threats, press with custom deal terms  

### Forbidden (never)

- Placing or answering phone calls (including “quick call” promises)  
- Collecting or holding cash  
- Confirming bookings without Nav date confirmation  
- Buying hardware, domains, or ads beyond budget  
- Mixing inventory or private data across Etsy shops  
- Posting customer portraits without consent  
- Deleting governance docs or audit logs  
- Expanding past v2 human gates on your own  

## Booking state machine

```text
inquiry → hold_proposed → hold_pending_nav → confirmed → completed
                ↘ rejected_by_nav / expired
```

Only Nav moves `hold_pending_nav` → `confirmed` (explicit message or calendar accept).

## Capacity rules (defaults)

| Parameter | Default |
|---|---|
| Session length | 45 min portrait / 30 min GenArt mini / 60 min letters |
| Buffer | 15 min between sessions |
| Max sessions / day | 6 |
| Hold TTL awaiting Nav | 24 h (then release or re-propose) |
| Lead time | ≥ 24 h for first-time customers |

## Approval artifacts

```text
docs/ops/approvals/
  catalog.md              # bookable session SKUs
  pricing.md              # price bands + ad budget cap
  brand_voice.md          # optional tone lock
  shops/
    <shop-id>.md          # per-Etsy-shop playbook
```

If `shops/` is empty, agent may prepare shop setup drafts but must ask Nav before going live on a new shop.

## Change control

1. Agent may PR ops doc improvements.  
2. Nav merges.  
3. Autonomy tier changes require editing this file’s tier heading.  

## Audit expectations

Log for publishes, listing changes, refunds, and booking transitions:

- timestamp, channel/shop, asset/order/booking id  
- rule checks, before/after for prices  
- Nav confirmation reference for date confirms and cash acks  
