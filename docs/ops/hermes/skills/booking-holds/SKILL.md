---
name: booking-holds
description: >
  Qualify session leads, propose 1-3 slots, place calendar holds (hold_pending_nav). Never mark confirmed until Nav confirms the date. Use for portrait/genart/letters session bookings.
compatibility: Hermes Agent; BotDraw mini-PC; Claude Max primary
metadata:
  brand: BotDraw
  owner: Nav
  autonomy: v2
---

# Booking Holds

## Flow
`inquiry → hold_proposed → hold_pending_nav → (Nav confirms) → confirmed`

## You may
- Propose slots within capacity rules (`GOVERNANCE.md`)
- Place holds; send “we’ll confirm the time shortly”
- Expire/release holds past TTL

## You must not
- Confirm final date/time yourself
- Promise phone calls
- Mark cash paid

## After Nav confirms
Send templated confirmation + what-to-bring; remind at −24h/−2h.
