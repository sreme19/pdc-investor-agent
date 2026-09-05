---
name: investor-outreach
description: Draft an outreach message (cold email, LinkedIn note, or warm-intro request) to an investor already logged in the pdc-investor-agent ledger, and log the touch once it's sent. Use when the user wants to reach out to a specific investor or work through a batch of the pipeline's `cold` list.
---

# Investor outreach

A drafting skill, not a sending skill — see `SPEC.md` decision 3. It writes the message; the human
sends it, from their own email/LinkedIn account, after reading it.

## Before you start

Run `pia pipeline` to see the current status and last-touch age for the investor in question. Read
any logged research notes for them (`pia note` entries show up nowhere else — there's no `pia show`
yet, so ask the user to paste the relevant note if you weren't the session that logged it, or re-run
`investor-research` first if none exists).

## Drafting

- Lead with the specific fit reason from the research note (portfolio overlap, thesis match), not a
  generic pitch — a message that could be sent to any fund reads as a mass blast and gets ignored.
  If no research is logged yet, say so and suggest running `investor-research` first rather than
  drafting blind.
- Prefer a warm-intro request over a cold email whenever one was logged — draft the ask to the
  connector, not to the investor directly, and say so clearly in the draft. A cold email or LinkedIn
  note is the fallback only when no warm path exists.
- Keep it short. A first touch is a hook for a reply, not the full pitch.
- Never fabricate traction numbers, prior investor names, or a "closing soon" framing that isn't true
  — see [[feedback_no_fabricated_numbers_research]] in memory; the same rule applies to outreach copy.

## After the human sends it

Log the touch — this is what keeps `pia pipeline` accurate:

```
pia touch --investor acme-vc --channel email --direction outbound \
  --summary "cold email referencing thesis fit + <comparable> portfolio company"
pia investor --id acme-vc --firm "Acme Ventures" --status contacted
```

If the summary quotes a figure — an amount discussed, a cheque range, a valuation — use
`--summary-file` with the text in a file instead of typing it inline. The shell eats `$` sequences
before `pia` sees them, and the figure disappears from the record with nothing left to detect it by
(`PILOT-LOG.md` L23). `pia` prints the figures it stored after each write; check them against what
you meant to say.

If a reply comes back later, log it too (`--direction inbound`) and move the status forward
(`meeting`, `diligence`, `committed`, `passed`, `declined`) as it actually changes — don't advance
status speculatively ahead of what's actually happened.

## Boundaries

- Never send an email, LinkedIn message, or any outbound communication yourself — see `SPEC.md`
  decision 3. Draft it, hand it to the user, and wait for them to send it before logging the touch.
- Never invent a warm-intro connection that wasn't actually logged by `investor-research` or stated
  by the user.
