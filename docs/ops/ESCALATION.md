# Escalation Guide

Ping Nav when any row matches. Use the owner’s preferred channel (Telegram/Slack/SMS — configure in agent runtime). Include: what happened, what you tried, recommended action, deadline.

## P0 — interrupt now

- Payment dispute, chargeback threat, or “you scammed me”  
- Safety / harassment / illegal request  
- Suspected data leak (customer photos, messages)  
- Mini-PC or BotDraw API down during booked sessions  
- Agent almost took a forbidden action (self-report)  

## P1 — same day

- Booking conflict it cannot resolve with buffers  
- Custom portrait + commercial likeness ask  
- Guest quote that looks like copyrighted lyrics  
- Refund / discount request  
- Press / influencer asking for collab  
- Calendar over capacity  

## P2 — in the next digest

- Soft FAQ the scripts don’t cover  
- Draft pack ready for weekly approval  
- Repeated no-shows / flaky leads pattern  
- Skill/process improvement proposals  
- Non-urgent job pipeline failures  

## Do not escalate

- Routine FAQ answered by script  
- Normal confirmed booking under rules  
- Single failed draft generation (retry, then digest)  
- Cosmetic IG caption A/B variants awaiting the weekly pack  

## Escalation message template

```text
[BotDraw Ops · P0|P1|P2]
What: …
Customer/asset: …
Risk: money | legal | brand | hardware | schedule
Tried: …
Need from Nav: approve | decide | take over
Deadline: …
Links: calendar · draft · job id
```
