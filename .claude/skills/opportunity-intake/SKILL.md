---
name: opportunity-intake
description: Process an investor, fund, accelerator, grant, competition or fundraising opportunity into the pdc-investor-agent pipeline, however it arrived — a pasted screenshot, a link, or an application form the user is already filling in. Extract who it is, log the sighting before anything else, run the eligibility gate, then verify every deciding field at the counterparty's own site. Use whenever the user pastes or attaches a screenshot of an investor post, fund page, programme listing or profile, sends a URL to one, or says they are entering, applying to or signing up for something.
---

# Processing an opportunity

The user's habit: they see a fund, angel, accelerator, programme or competition somewhere — usually
LinkedIn — and drop it into this session. Follow this order every time one shows up.

## 0. This is the path even when it does not arrive as a screenshot

The trigger is an **opportunity**, not an image. It has arrived as all of these:

- a screenshot, which is the original case and the one below is written for;
- **a bare link with "i am entering this competition"** — that is an opportunity, and on
  2026-09-07 it was worked start to finish without this skill, so nothing was logged and the
  ledger has no record of it (handoff §4);
- **an application form the user is already typing into**, which is the same thing arriving later
  in its lifecycle. Helping fill in fields is not a reason to skip the gate — it is the moment the
  gate is worth most, because a form asks the deciding questions out loud.

If you are about to help with an opportunity's *content* — a form answer, a pitch, a
one-liner — and no ledger record exists, stop and do steps 2 and 3 first. They take a minute
between them. The failure is not hypothetical: it has happened once, and the cost was a competition
whose deadline had already passed a week earlier, discovered after the founder had written his
answers.

**A screenshot is a claim; a link is not better.** No script has read either. You are the reading
step for both.

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

## 1. Read the source

Pull out everything visible: the firm/programme name, what they claim to be (fund, angel,
accelerator, programme, grant, intermediary), the ask, cheque size, stage, deadline, how you are
meant to apply, and who posted it.

If the name is unreadable or ambiguous, ask. A wrong name poisons every record downstream, and
`pia` cannot tell you it happened.

**Note who runs it, separately from what it is called.** One organiser routinely runs several
things at once — on 2026-09-07 the same organiser had a written application (closed) and a social
contest (open a month later) around one event, with different deadlines and different submission
routes. Those are two records sharing an `--organiser`, never one record. Conflating them points
the founder at the wrong deadline, and `pia pipeline` can only warn you about it if the organiser
slug is set on both (L37).

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
- **Is the form still accepting entries, and is that the same question?** It is not. On 2026-09-07
  the published window had closed a week earlier and the form was live, required, and taking
  answers. Record what you observed with `--submission-state`, and never infer the window from the
  route. A form that accepts input proves only that nobody switched it off.

### The founder block — ask once, keep it

Several of these turn on facts about **the founder**, not the counterparty: age, residency,
citizenship, whether an entity is registered and where, whether the startup is "operating in
India". This repo holds none of them, so every application form asks and every session
re-establishes them by hand. In the pilot a residency clause was the single fatal criterion, and it
was settled in under a minute *because it was asked rather than inferred* (L12, L20).

So **ask, every time, and never infer**. Not from the repo, not from a resume, not from an earlier
draft. A wrong residency or entity answer on an application form is a false declaration, not a typo,
and it is the founder's signature on it.

**These answers currently have nowhere to persist, and that is an open gap, not an oversight.** The
ledger has three record kinds — investor, touch, note — all of which hang off a counterparty id, so
a founder fact can only be stored by inventing a fake counterparty, which would then appear in
`pia pipeline` as an unscreened record with a deadline of nowhere. That is worse than asking again.
Until there is a record kind for it, put the answer in the `screening` reason for the opportunity it
decided, where it is at least attached to the verdict it produced, and expect to re-ask on the next
one. Tracked as `PILOT-LOG.md` L36's sibling — it has now cost a round-trip twice.

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
  --organiser <slug, when this organiser runs more than one thing> \
  --stage-focus "<stage>" --check-size '<$ figure — SINGLE quotes>' \
  --deadline <YYYY-MM-DD | YYYY-MM | rolling> \
  --deadline-source <first-party-page|form-itself|press|social> \
  --submission <form|email|dm|warm-intro|event|other> \
  --submission-state <observed-accepting|observed-closed|unknown> \
  --source-url "<the page you verified on>"
```

Single-quote anything containing a `$`. In double quotes the shell eats it.

Leave a field blank when the counterparty does not publish it. A blank is honest; a plausible number
with no first-party source is the thing this whole loop exists to prevent.

### The deadline needs to say where it came from, and `pia` now refuses it otherwise

`--deadline` without `--deadline-source` is rejected at the write. Twice the deciding date has had
no first-party page behind it (L35):

- 2026-09-06: the only source was a social caption, and that deadline had already been extended once.
- 2026-09-07: the organiser's site 403'd every fetch; the closing date existed only in the
  organiser's **own editorial coverage of its own programme**. The form stated no date at all.

**The organiser's newsroom is `press`, not `first-party-page`.** That distinction is the whole
point of the field. "First-party" is a claim about where *this field* came from, not about whose
website you were on — L19's per-field rule applied to provenance. A `press` or `social` deadline
prints as `[UNVERIFIED]` in `pia show` and `pia pipeline` forever after, which is the correct
reading of it, not a nag to be cleared.

If two of the counterparty's **own** pages disagree about a field, do not pick a winner silently.
Mark it: `--conflicting-fields deadline`. L34 found this with a **venue** — the field somebody
books a flight against — published two ways on two of the organiser's own domains. A field nobody
can trust must read as untrusted, not as verified with a caveat buried in prose.

## 5. Research and log it

Now hand off to the **`investor-research`** skill's method: thesis fit, portfolio overlap, stage and
cheque fit, and the most credible warm-intro path. Log it with `pia note --kind research
--summary-file`, and put explicit `NOT confirmed on their own site` markers on anything you could
not verify in step 4.

If what you found is about the *sector* rather than this counterparty, it has nowhere good to live —
every note hangs off an investor id (L17). Write it to `ledger/RESEARCH-category-<topic>.md`; the
Numbers sheet's **Research Files** tab lists it as relating to no single record, which is at least
visible.

## 6. If it asks for traction, quote a dated block — never compute one inline

Application forms ask for proof of use, usually under a clause saying false claims mean
disqualification. On 2026-09-07 that question was answered by computing counts against the
product's production database, live, mid-form. It worked, and it was the wrong way round: two of
the obvious phrasings of those numbers were wrong **in the flattering direction** until they were
checked, and only checked because a number looked too good.

**The numbers do not live in this repo.** They live in `pocket-dating-coach`, and the definitions
that make them true or false live in `pocket-dating-coach/docs/investor-metrics-proposal.md`. Read
that file before quoting any product figure. Three things in it are load-bearing:

1. **`is_seed` / `is_provisional`.** Member counts must exclude seeded and provisional profiles.
2. **`is_ai`.** Over half the in-app message volume is the product's own sends. "Matches with a
   conversation in them" reads 570 of 573 unfiltered and 322 of 573 on human messages only. The
   unfiltered number is an artefact, and it is the one that flatters.
3. **The 1000-row cap.** `supabase-js` truncates a `select` at 1000 rows with no error and no
   warning — just a short array. The same distinct-count read 257 capped and 570 paginated. Any
   figure built from row sets rather than an exact head-count has to paginate and assert the total
   before it is quoted.

**Before aggregating member data at all, check the privacy prerequisite in that same file.** It has
stood since 2026-09-04: the app's privacy policy does not mention aggregate analytics, and under
DPDP purpose limitation the clause is supposed to land before member data is aggregated for
fundraising. On 2026-09-07 it had not landed and the figures went to a third party anyway — not
because any rule was broken, but because the constraint lives in the repo that owns the data and
the session ran in this one. If the clause still is not there, say so to the founder and let them
decide; do not decide silently by proceeding.

State the filter beside every figure you hand over. "170 members" and "170 members excluding seeded
and provisional" are different claims, and only one of them survives somebody asking.

## 7. Stop. Do not draft.

Research and a verified record are the finished work product for a screenshot. State the fit verdict
plainly and stop there.

Only draft when the user explicitly asks, for that specific counterparty — and then use the
**`investor-outreach`** skill. In a batch, one "draft it" covers one counterparty, not the rest.

Before drafting anything that quotes traction, check `ledger/FACT-SHEET.md` and its date. A figure
with no dated source is unavailable, not a number. The fact sheet is human-supplied; you cannot go
and refresh it, because this repo holds no Supabase credential and that is deliberate
(`SPEC.md` decision 4).

## 8. Hand it back

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
