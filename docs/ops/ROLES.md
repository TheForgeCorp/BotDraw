# Roles & Responsibilities

## RACI (v2 — full digital ops)

| Domain | Operator agent | Nav (owner) | Engineering (this repo / Cursor) |
|---|---|---|---|
| Brand strategy & public name lock | C / propose | **A** | C |
| Website run, content, forms, uptime | **A/R** | I (overrides) | C (platform hooks) |
| Instagram post + reply (DM/comment) | **A/R** | I | I |
| Etsy shop(s) listings, orders, messages | **A/R** | I | C (export/fulfill APIs) |
| Ads / paid boost within budget cap | **R** | **A** (set budget) | I |
| Lead intake & CRM | **A/R** | I | C |
| Propose booking slots + holds | **A/R** | — | C (calendar) |
| **Confirm booking dates** | Propose only | **A/R** | I |
| **Cash collection** | Track / remind | **A/R** | I |
| **Phone calls** | Never | **A/R** | I |
| Platform digital payments (Etsy etc.) | **R** (within policy) | **A** (payout accounts) | C |
| Refunds within published shop policy | **R** | C (exceptions) | I |
| Pricing inside approved bands | **R** | **A** (bands / catalog) | I |
| BotDraw stack monitor/maintain | **A/R** | I | **R** (code) |
| Plotter hardware purchase | I | **A/R** | C (drivers) |
| Legal / tax / entity | Escalate | **A/R** | C |
| Governance docs | Propose edits | **A** | **R** (repo) |

**R** = does the work · **A** = accountable / final say · **C** = consulted · **I** = informed

## Role cards

### Operator agent (“BotDraw Ops”)

- Full digital GM: website, Instagram, Etsy (N shops), BotDraw services  
- Publishes and replies on owned channels without waiting for content approval batches  
- Manages listings, inventory flags, order messages, and policy-bound refunds  
- Proposes booking dates, places holds, sends async confirmations after Nav confirms  
- Maintains mini-PC processes, restarts, log triage, and backup checks  
- Builds daily **date-confirm queue** and **cash-to-collect** lists for Nav  
- Never handles cash or phone calls  

### Nav (principal)

- Confirms (or reschedules) booking dates  
- Collects cash and marks cash invoices paid  
- Takes all phone calls  
- Sets brand lock, price bands, shop roster, ad budgets  
- Buys hardware / opens bank & payout accounts  
- Can override any agent action  

### Engineering

- Ships BotDraw software, emulator, deploy scripts  
- Exposes APIs for jobs, health, exports the operator uses to fulfill  
- Keeps this governance pack in git  

## Named agent personas (optional routing)

| Persona | Focus | Publish? | Reply customers? | Propose bookings? |
|---|---|---|---|---|
| `ops-web` | Website CMS/uptime | Yes (site) | Form replies | Soft holds |
| `ops-ig` | Instagram | Yes | DM/comment | Soft holds |
| `ops-etsy` | Each Etsy shop | Listings | Etsy messages | No (product orders) |
| `ops-booker` | Sessions calendar | No | Booking async | Yes → Nav date confirm |
| `ops-sre` | Mini-PC / BotDraw / site health | Status posts if needed | No | No |

Single-agent deployments must still obey the same boundaries.
