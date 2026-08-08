# Turn 3 — Confirm (restyle knobs only; no re-ingest)

**Don't hand-copy the schema from source anymore.** Run:

```bash
botdraw vision brief <job_id> --turn 3
```

Writes the exact prompt + images + save-the-reply instructions to a
folder (see `turn1_scene.md` for the general flow).

Notes specific to this turn: `force_reingest` should come back `false` —
this turn only adjusts restyle knobs, it never re-ingests. Do not accept
if a clear interior accent stroke from the photo is still missing.
