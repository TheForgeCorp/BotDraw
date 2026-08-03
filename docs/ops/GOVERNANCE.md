# Governance & Decision Rights

## Autonomy tier: v1 — Book + Draft

Frozen until Nav promotes the tier in writing (commit or message that updates this file).

### Allow (agent executes)

- Create/update/cancel **holds** on the shared calendar  
- **Confirm bookings** when all of these are true:
  - Requested slot free + buffer rules satisfied  
  - Service type is in the approved catalog  
  - Customer contact + consent fields present  
  - No legal/IP flag from intake  
- Send **templated** confirmations, reminders, and “what to bring” notes  
- Draft website/IG/email/SMS copy into an approval queue  
- Capture leads, tags, and follow-up dates  
- Produce daily/weekly digests for Nav  
- Read BotDraw job/export metadata for status answers (“your hatch job finished”)  

### Ask first (Nav must approve)

- Any public publish or schedule (IG, site, newsletter, ads)  
- New package, price, discount beyond a listed promo code  
- Off-catalog custom art promises  
- Same-day rush that breaks buffer rules  
- Use of customer photos beyond the session (portfolio) without explicit consent record  
- Partner/collab shoutouts  

### Forbidden (never)

- Spending money or moving funds  
- Ordering hardware/supplies  
- Claiming a public brand name that isn’t approved  
- Posting customer portraits without consent flag  
- Running unattended physical plot jobs as “sold” if hardware isn’t commissioned  
- Expanding autonomy tier on your own  
- Deleting governance docs or audit logs  

## Capacity rules (defaults — edit with Nav)

Until a live calendar config exists, treat these as policy:

| Parameter | Default |
|---|---|
| Session length | 45 min portrait / 30 min GenArt mini / 60 min letters consult+plot |
| Buffer | 15 min between sessions |
| Max sessions / day | 6 |
| Lead time | ≥ 24h for first-time customers |
| Same-day | Escalate to Nav |
| Deposit | Nav-defined; agent only cites published policy |

## Approval artifacts

Store or link approvals so audits are easy:

```text
docs/ops/approvals/
  YYYY-MM-DD-content-pack.md   # Nav-approved posts for a window
  pricing.md                   # current packages (Nav-owned)
  catalog.md                   # bookable SKUs
```

If those files are missing, **draft only** for marketing; **book only** generic “intro consult” if catalog is empty — otherwise escalate.

## Change control

1. Agent may open a PR / patch proposal for ops docs.  
2. Nav merges or rejects.  
3. Autonomy tier changes require an explicit edit to this file’s “Autonomy tier” section.  

## Audit expectations

For every booking and every publish request, record:

- timestamp  
- customer / asset id  
- rule checks passed/failed  
- approval reference (or “auto under v1 booking rules”)  
- channel message ids when available  
