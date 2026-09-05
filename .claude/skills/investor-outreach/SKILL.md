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

## Before drafting: check the eligibility verdict

`pia show <id>` prints it directly under the status, always, even when it is unset. Read it.

- **`eligible`** — proceed.
- **`ineligible`** — do not draft. The record names the published criterion we fail. Tell the user
  which one, and stop.
- **`UNSCREENED`** — nobody has checked this counterparty against their own published criteria.
  Do not draft. Run the eligibility gate first (the `opportunity-intake` skill, step 3) and record
  the verdict with `pia screen`.

A draft is cheap to write and expensive to send to a fund that excludes consumer dating by policy.
The `cold` list is not a list of qualified counterparties; it is a list of ones nobody has ruled out
yet, which is a different thing entirely (`PILOT-LOG.md` L8, L31).

Note what this rule is and is not. `pia` refuses to *log* an outbound touch on an unscreened record,
which catches the mistake at the first moment the tooling is involved — but that is after the human
has already sent. Nothing in this repo sits upstream of a draft. So this check is yours to make, and
skipping it is not something anything else will catch for you.

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

If this refuses with `nobody has screened ...`, the eligibility gate was skipped and a message has
already gone out to a counterparty nobody checked. Say so to the user plainly rather than quietly
adding `--force-unscreened`. The override exists for a deliberate, explained exception — it records
itself on the touch — not for getting past a gate that just did its job.

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
