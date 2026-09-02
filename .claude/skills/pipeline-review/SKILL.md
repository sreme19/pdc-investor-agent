---
name: pipeline-review
description: Summarize the investor pipeline for Pocket Dating Coach (Riteangle) — who's stalled, who needs a follow-up, what's approaching a decision — from the pdc-investor-agent ledger. Use when the user asks for a fundraise status update, or on a recurring cadence as a review reminder.
---

# Pipeline review

A read-and-summarize skill. It never contacts anyone and never changes a status itself — it surfaces
what a human should look at and act on.

## What to run

```
pia pipeline
pia stats
```

## What to look for

1. **Stalled contacts** — anyone `contacted` with no reply and no touch in the last ~10 business days.
   Flag as due for a follow-up.
2. **Meetings without a next step** — a `meeting`-status investor with no `note --kind meeting`
   logged, or a meeting note with an empty `--next-steps`. That's a dropped thread, not just slow.
3. **Stage concentration** — how many investors sit at each status. A pipeline that's all `cold` with
   nothing moving past `contacted` is a signal to revisit the outreach approach, not just push harder
   on volume.
4. **Committed but not yet closed** — anyone at `committed` needs the human to track the actual legal/
   wire process outside this ledger; this repo only tracks the relationship, never deal execution or
   money movement (see `SPEC.md` decision 3).

## Reporting back

Give the user a short, prioritized list: who to follow up with this week, who needs a status update
logged (a meeting happened but was never recorded), and the overall shape of the pipeline. Don't log
anything yourself in this skill — if a status is genuinely stale, tell the user and let them (or the
`investor-outreach` skill, after the actual touch happens) update it.
