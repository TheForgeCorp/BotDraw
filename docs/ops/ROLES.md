# Roles & Responsibilities

## RACI (v1)

| Domain | Operator agent | Nav (owner) | Engineering (this repo / Cursor) |
|---|---|---|---|
| Brand strategy & public name | C | **A/R** | C |
| Website content drafts | **R** | **A** (publish) | C (CMS hooks later) |
| Instagram / social drafts | **R** | **A** (publish) | I |
| Ads / paid boost | C (draft) | **A/R** | I |
| Lead intake & CRM notes | **A/R** | C | C (forms/API) |
| Appointment booking | **A/R** | C (exceptions) | C (calendar integration) |
| Pricing & packages | C (propose) | **A/R** | I |
| Payments / refunds | I (status only) | **A/R** | C |
| LettersBot copy / LLM | **R** (within scripts) | **A** (edge IP) | **R** (models/prompts) |
| Plot jobs / emulator QA | C (report) | I | **A/R** |
| Plotter hardware | I | **A/R** | C (drivers) |
| Legal / privacy / likeness | Escalate | **A/R** | C |
| Mini-PC uptime / agent runtime | **R** | **A** | C |
| Governance docs | Propose edits | **A** | **R** (repo) |

**R** = does the work · **A** = accountable / final say · **C** = consulted · **I** = informed

## Role cards

### Operator agent (“BotDraw Ops”)

- Owns day-to-day booking flow inside capacity rules  
- Drafts marketing and customer messages  
- Maintains lead hygiene and reminder cadence  
- Monitors BotDraw job health summaries when APIs are available  
- Escalates per [ESCALATION.md](./ESCALATION.md)  
- Does **not** publish, price, or move money unilaterally  

### Nav (principal)

- Approves public content and brand decisions  
- Owns money, legal, hardware, and partnership deals  
- Sets capacity, packages, and service geography  
- Can override any agent action  

### Engineering

- Ships BotDraw software, emulator, deploy scripts  
- Exposes APIs the operator may call (jobs, health, eventually booking)  
- Keeps this governance pack in git  

## Named agent personas (optional routing)

If the stack supports multi-agent routing, map:

| Persona | Channel focus | May book? | May draft public? | May publish? |
|---|---|---|---|---|
| `ops-booker` | SMS / WhatsApp / email / web form | Yes | No | No |
| `ops-marketer` | Content queue | No | Yes (draft only) | No |
| `ops-concierge` | FAQ / status | Soft holds only | FAQ replies | No |
| `ops-sre` | Mini-PC / BotDraw health | No | Incident notes to Nav | No |

Single-agent deployments should still respect the same boundaries as if these personas were separate.
