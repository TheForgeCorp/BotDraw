# Escalation Guide

Ping Nav when any row matches. Preferred channels: async only (Telegram/Slack/SMS — configure in runtime). Include: what, tried, need, deadline.

## P0 — interrupt now

- Needs a **phone call** (customer insists / safety / fraud)  
- **Cash** dispute or cash session starting without Nav available  
- Payment chargeback / “scam” accusation  
- Safety / harassment / illegal request  
- Suspected data leak  
- Website + IG + Etsy or BotDraw down during active orders/sessions  
- Agent almost violated date/cash/phone gates (self-report)  

## P1 — same day

- Holds stuck in `hold_pending_nav` approaching TTL  
- Booking conflict Nav must pick between  
- Off-policy refund or custom commercial deal  
- New shop / domain / payout account needed  
- Ad budget would exceed cap  
- Guest quote / likeness IP risk  
- Press or large collab  

## P2 — in the next digest

- Content performance notes  
- Soft FAQs to fold into scripts  
- Non-urgent job failures (retry exhausted)  
- Skill/process improvement proposals  
- Price-band tweak proposals  

## Do not escalate

- Routine IG posts/replies and Etsy messages inside policy  
- Normal holds awaiting Nav’s date confirm (list them in digest, don’t spam)  
- Successful platform checkouts  
- Single service restart that recovered  

## Human action queues (every digest)

```text
DATE CONFIRM:
  - booking_id · customer · proposed slots · hold expiry

CASH TO COLLECT:
  - invoice_id · customer · amount · when/where

PHONE NEEDED:
  - why · customer · callback window · context link
```

## Escalation message template

```text
[BotDraw Ops · P0|P1|P2]
What: …
Shop/channel/booking: …
Risk: cash | phone | date | legal | stack | brand
Tried: …
Need from Nav: confirm-date | collect-cash | call | decide
Deadline: …
Links: …
```
