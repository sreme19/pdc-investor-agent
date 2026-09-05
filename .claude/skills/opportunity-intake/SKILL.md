---
name: opportunity-intake
description: Process a pasted screenshot of an investor, fund, accelerator, grant or fundraising opportunity into the pdc-investor-agent pipeline — extract who it is, log the sighting before anything else, run the eligibility gate, then verify every deciding field at the counterparty's own site. Use whenever the user pastes or attaches a screenshot of an investor post, fund page, programme listing or profile in this repo.
---

# Processing a pasted opportunity screenshot

The user's habit: they see a fund, angel, accelerator or programme somewhere — usually LinkedIn —
screenshot it, and paste it into this session. No script has read that image. You are the vision
step. Follow this order every time one shows up.

**Do the research and drafting yourself, in this conversation.** This repo holds no Anthropic API
key and never will (`SPEC.md` decision 1). The CLI only persists what you decide; you already have
web access and can write text yourself.

**Never contact anyone and never move money** (`SPEC.md` decision 3). This skill ends at a logged,
verified record. Sending is the human's, always.

## Why this order and not the obvious one

The obvious order is: read it, research it, decide. The pilot ran that order four times and it was
wrong every time — full research was spent on all four opportunities *before* anyone checked whether
they were eligible, and three died on published eligibility or on not being an investor at all
(`PILOT-LOG.md` L8). So screening comes before research, and verification comes before belief.

The other thing the pilot established: a screenshot is a **claim**, not a fact. One post implied an
immediate deadline that the programme's own site put five months out. One described itself as an
investor in the headline and an intermediary two lines down. One aggregator's cheque size differed
from the fund's own published figure by about 6x (L6, L19). Treat everything in the image as
hearsay until you have seen it on the counterparty's own page.

## 1. Read the screenshot

Pull out everything visible: the firm/programme name, what they claim to be (fund, angel,
accelerator, programme, grant, intermediary), the ask, cheque size, stage, deadline, how you are
meant to apply, and who posted it.

If the name is unreadable or ambiguous, ask. A wrong name poisons every record downstream, and
`pia` cannot tell you it happened.

## 2. Log the sighting, before anything else

Do this even if you go no further. An opportunity that dies in a conversation the user later closes
is the fault `PILOT-LOG.md` L2 exists for.

```bash
cat > /tmp/seen.md <<'EOF'
<what the post actually claimed: ask, cheque size, stage, deadline, how to apply, who posted it>
EOF

pia intake --id <slug> --firm "<name as the post gives it>" --seen-file /tmp/seen.md \
  --source "LinkedIn screenshot" --source-url "<the post URL, if you have it>"
```

Use `--seen-file`, not `--seen`. Text typed inline goes through the shell, which expands `$500k` to
nothing before `pia` runs, and the figure is gone with nothing left in the string to notice it by
(`PILOT-LOG.md` L23 — this corrupted a real record). Read the `stored N chars · figures: …` line
that comes back and check the figures against the post.

`intake` deliberately has **no** `--check-size`, `--deadline`, `--stage-focus` or `--submission`
flags. Those fields hold figures read off the counterparty's own site. What the post claimed goes
into the sighting note as prose, where it stays visibly a claim. Do not route around this by calling
`pia investor` with numbers off the screenshot.

Add `--kind` only if the post genuinely says what they are. Half a fundraise pipeline is not a fund
(L7), and guessing wrong is worse than leaving it blank.

## 3. Eligibility gate — cheap, fatal checks only

Before any real research. You are looking for reasons to stop, not reasons to proceed:

- **Are they actually an investor?** Intermediaries, listing platforms and brokers describe
  themselves in investor language. Establish the fee structure before anything moves.
- **Is the sector excluded?** Consumer dating gets excluded by name more often than you would expect.
- **Is a for-profit company eligible?** Grant pools frequently exclude one.
- **Is the geography workable?**
- **Does it require relocation?** This one needs a threshold, not a keyword match (L20). A long-term
  relocate-and-build-a-team clause is fatal. A three-week in-person residency is travel, which the
  founder's constraints permit. A gate matching on the word "relocate" would have thrown away a
  live, well-matched opportunity in the pilot.
- **Is the window actually open?** Closed with an unannounced reopen is a real state, and neither
  `rolling` nor a date nor blank tells the truth about it (L18). Say so in prose.

**Record the verdict either way — including when they pass.** This is what `pia screen` is for:

```bash
cat > /tmp/why.md <<'EOF'
<what you actually read on their own site, and where>
EOF

pia screen --investor <slug> --verdict eligible|ineligible \
  --criterion "<the published rule that decided it>" --reason-file /tmp/why.md
```

Both `--criterion` and `--reason` are required, and that is deliberate: a verdict nobody can check
is the same problem as no verdict, moved into a new field.

`--verdict ineligible` sets `status` to `screened-out` for you. `screened-out` means *we* ruled them
out; `passed` means *they* said no after contact. Never use one for the other — six months on, the
difference is the whole story. Then stop.

Until a record is screened `eligible`, **`pia touch --direction outbound` will refuse to log**. That
is a deliberate tripwire, not an obstacle to route around. If you hit it, the answer is to run the
gate, not to reach for `--force-unscreened`.

**A well-evidenced "no" is the most valuable output of this loop** (L11). Say so plainly to the user
rather than treating it as a wasted pass.

## 4. Verify at the counterparty's own site, field by field

Not "verify the record" — verify each field. Two of nine counterparties in the pilot published no
cheque size, no stage and no submission route anywhere on their own site (L19).

- **Aggregators are not sources.** Crunchbase, Tracxn, listicles and "top 20 funds" posts fill the
  vacuum with numbers that are routinely wrong. If the counterparty does not publish a figure, the
  figure is **unavailable**, not whatever an aggregator says. Record the absence.
- **A 200 is not a verification.** Several counterparty sites render their own headline totals as
  literal zeros or `$0 Mn+` placeholders. The page loads and publishes a non-number (L24).
- **On a 404 or a redirect, re-derive their identity before recording an absence** (L25). One
  counterparty had rebranded: old domain 301s, old founder path 404s, every aggregator still cited
  the dead URL. Stopping at the 404 would have concluded "publishes nothing for founders" about the
  counterparty with the most specific founder page in the whole pass.
- **If the site cannot be read at all** — a hard 403, a bot wall that a real browser session also
  hits — that is a third state (L24). It is not "nobody checked yet". Mark it a lead, not a
  counterparty, say explicitly that drafting must not proceed from it, and tell the user it needs a
  human to open the page by hand.

To see a LinkedIn profile or post, use the `claude-in-chrome` browser tools — the user's own
logged-in Chrome. LinkedIn blocks unauthenticated fetches, including the in-app Browser pane, with a
999 or a sign-up wall. Read the poster's own follow-up comments too; they carry updates like
"applications closed". Close any tab you opened.

Then write the verified fields — and only the verified ones:

```bash
pia investor --id <slug> --firm "<their current name>" --kind <kind> \
  --stage-focus "<stage>" --check-size '<$ figure — SINGLE quotes>' \
  --deadline <YYYY-MM-DD | YYYY-MM | rolling> --submission <form|email|dm|warm-intro|event|other> \
  --source-url "<the page you verified on>"
```

Single-quote anything containing a `$`. In double quotes the shell eats it.

Leave a field blank when the counterparty does not publish it. A blank is honest; a plausible number
with no first-party source is the thing this whole loop exists to prevent.

## 5. Research and log it

Now hand off to the **`investor-research`** skill's method: thesis fit, portfolio overlap, stage and
cheque fit, and the most credible warm-intro path. Log it with `pia note --kind research
--summary-file`, and put explicit `NOT confirmed on their own site` markers on anything you could
not verify in step 4.

If what you found is about the *sector* rather than this counterparty, it has nowhere good to live —
every note hangs off an investor id (L17). Write it to `ledger/RESEARCH-category-<topic>.md`; the
Numbers sheet's **Research Files** tab lists it as relating to no single record, which is at least
visible.

## 6. Stop. Do not draft.

Research and a verified record are the finished work product for a screenshot. State the fit verdict
plainly and stop there.

Only draft when the user explicitly asks, for that specific counterparty — and then use the
**`investor-outreach`** skill. In a batch, one "draft it" covers one counterparty, not the rest.

Before drafting anything that quotes traction, check `ledger/FACT-SHEET.md` and its date. A figure
with no dated source is unavailable, not a number. The fact sheet is human-supplied; you cannot go
and refresh it, because this repo holds no Supabase credential and that is deliberate
(`SPEC.md` decision 4).

## 7. Hand it back

Tell the user:

- what the counterparty actually is, in plain language
- the eligibility verdict as recorded by `pia screen`, and which specific published criterion
  decided it
- which fields you verified at source, and which you could not — by name
- the recommended next move, or an explicit "nothing to do here, and here is why"

The sheet updates itself: every `pia` write mirrors into
`ledger/PDC Investor Pipeline 2026.numbers`. Point the user at it if they want to see where the
record landed. If a write printed `sheet NOT updated`, it is almost always because the sheet is open
in Numbers — say so, and run `pia sheet` once they have closed it.
