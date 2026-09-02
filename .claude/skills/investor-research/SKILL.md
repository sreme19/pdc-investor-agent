---
name: investor-research
description: Research a prospective investor for Pocket Dating Coach (Riteangle) — thesis fit, stage/check-size fit, portfolio overlap, and the most credible warm-intro path — and log the result to the pdc-investor-agent ledger. Use when the user names a fund or angel to look into, or wants the pipeline enriched before a batch of outreach.
---

# Investor research

A read-and-record skill. It never contacts the investor and never sends anything — see `SPEC.md`
decision 3. It exists so outreach starts from an actual fit assessment instead of a cold guess.

## Before you start

Run `pia pipeline` (from this repo) to see who's already logged and at what status, so you don't
duplicate research on an investor already past `cold`.

## What to research

1. **Thesis fit** — does the fund/angel state a stage, check size, and sector focus that plausibly
   includes a consumer dating/relationships app? Pull this from the fund's own site or public
   one-pager, not from a third party's summary of it.
2. **Portfolio overlap** — any existing portfolio companies in dating, relationships, consumer social,
   or adjacent consumer subscription products. A close comparable (successful or not) is worth noting
   either way — it tells you what story they already believe or are skeptical of.
3. **Check size and stage** — does it match Pocket Dating Coach's current round? Note explicitly if a
   fund only leads or only follows, since that changes how the ask should be framed later (a decision
   left to the outreach skill, not this one).
4. **Warm-intro path** — the single most credible path in: a shared connection, a portfolio founder
   who'd vouch, a shared investor already in the round, or an event/community both are part of. A cold
   email is the fallback, not the plan.

## Logging what you find

If the investor isn't in the ledger yet, add them first:

```
pia investor --id acme-vc --firm "Acme Ventures" --stage-focus seed --check-size "$25k-100k" \
  --source "found via <how>" --status cold
```

Then log the research as a note, with the warm-intro path (if any) in `--next-steps`:

```
pia note --investor acme-vc --kind research \
  --summary "Seed-stage consumer fund; portfolio includes <comparable>; thesis emphasizes retention over acquisition" \
  --next-steps "warm intro via <name>, portfolio founder at <company>"
```

## Reporting back

Summarize the fit assessment in plain language and state your confidence in the warm-intro path
explicitly (confirmed connection vs. a plausible but unverified one). Don't decide whether to reach
out — that's a call for the user or the `investor-outreach` skill to make from the logged research, not
this one.
