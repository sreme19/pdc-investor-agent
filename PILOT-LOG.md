# Pilot log — LinkedIn opportunity intake

Running record of friction and gaps found while working real investment opportunities by hand, so
the repeatable version gets engineered from evidence rather than guesses.

**Rule for this file:** process observations only. No real investor/fund names, no check sizes, no
deal terms — those belong in the gitignored `ledger/` (`SPEC.md` decision 2). This file is
committable; keep it that way.

Statuses: `open` (still a real gap) / `fixed` (built) / `dropped` (turned out not to matter).

## Session 1 — 2026-09-05

### L1 — Repo was not runnable on arrival · open
No venv, no ledger dir; `pia` was not on PATH. Cost a setup round-trip before any real work.
Candidate fix: a `make setup` / one-liner bootstrap, or a first-run check inside the skills.

### L2 — No intake path for a screenshot-sourced opportunity · open
The three existing skills assume you already have a *named* fund to research. This session starts
from a LinkedIn screenshot: an image → extract fund/program, ask, stage, check size, deadline, and
the submission mechanism (form / email / DM / comment) → decide fit → then hand off to
`investor-research`. Nothing covers that first hop, and the mechanism + deadline fields have no home
in the ledger schema today.
Candidate fix: an `opportunity-intake` skill, plus a place to record deadline and how-to-apply.

### L3 — Applications are not the same shape as outreach · open
`investor-outreach` drafts a message to a person. An accelerator/fund application is a form with
fixed questions and word limits, and the same core facts get retyped for every one.
Candidate fix: a reusable fact sheet (traction, round, team, ask) the drafting step pulls from, so
answers stay consistent across applications and nothing gets improvised per-form.

### L4 — No `pia show <id>` · FIXED (session 2)
Already flagged in `SPEC.md` "Not built yet". Confirmed as real friction the moment a second session
has to pick up an investor logged by the first — `investor-outreach` currently works around it by
asking the user to paste the note back in.

### L5 — Ledger vocabulary may not fit "applied" · superseded by L13
Statuses are `cold → contacted → meeting → diligence → committed → passed/declined`. Submitting an
application is not quite `contacted`, and it carries a decision date the pipeline can't represent.
Watch whether this actually bites during the pilot before changing the schema.

### L6 — LinkedIn posts misstate urgency and terms; verify at source every time · confirmed
Highest-value finding of the session. One post implied an immediate opportunity; the programme's own
site put the deadline five months out. Another was a third party's marketing summary of a sovereign
programme, not an official channel — figures reproduced without a source. A third described itself as
an investor in the headline and as an intermediary two lines down.
Candidate fix: make "verify against the programme's own site before any drafting" a mandatory,
non-skippable step of the intake loop, and record the source URL alongside every claim.

### L7 — Half of these are not investors, and the schema says they are · FIXED (session 2)
Of four opportunities: one accelerator with a mandatory relocation clause, one sovereign
grant/investment programme, one fundraising intermediary of unknown fee structure, one open-source
public-goods grant pool. Only the schema's `investor` noun was available, so `--check-size` and
`--stage-focus` got stuffed with prose that doesn't compare across records, and the deciding fields —
deadline, relocation requirement, submission mechanism, eligibility verdict — have no home at all.
Candidate fix: an `opportunity` record kind, or explicit `--kind`, `--deadline`, `--source-url` fields.

### L8 — Screening out is most of the value; do it before research, not after · confirmed
Two of four failed on published eligibility, one on counterparty verification. Full research was done
on all four before that was known, which is backwards.
Candidate fix: a cheap eligibility gate as step one — fatal-disqualifier checks (for-profit excluded?
sector excluded? relocation required? actually an investor?) before any deep research spend.

### L9 — No fact sheet, and no traction facts to build one from · BLOCKING
Confirms L3 and makes it worse. Searched the product repo for anything usable in an application:
nothing beyond a dev-database row count from four months prior. No user numbers, revenue, retention,
or launch status exists in any committed file. Every application asks for exactly these, so drafting
is blocked on the human regardless of how good the tooling gets.
Candidate fix: a fact sheet is the *first* artifact the repeatable loop needs, and it has to be
human-supplied and dated. The loop should refuse to draft against a stale or empty one rather than
improvise numbers.

### L10 — Traction numbers must be pulled from the source of truth, never recalled · confirmed, high value
The numbers offered from memory were ~6x the actual database figures, and the repo's own docs carried
a stale count from four months earlier. Neither was usable. A direct read of production settled it in
one command and also surfaced the genuinely strongest fact — a growth rate — that nobody had in mind.
Candidate fix: the loop pulls counts itself and writes a dated fact sheet; drafting reads only from
that file, and refuses to run against one older than ~2 weeks. Resolves L3 and L9 together.

### L11 — The loop's most valuable output is a well-evidenced "no" · confirmed
Four opportunities in, zero applications out, and that is the correct result: two failed published
eligibility, one failed counterparty verification, one failed a founder constraint. The time saved is
the return. A loop optimised for "drafts produced" would have manufactured four bad applications.
Candidate fix: design the loop to report screened-out with reasons as a first-class success outcome,
and record the disqualifying criterion verbatim so the same opportunity isn't re-researched next time
it circulates on LinkedIn.

### L12 — Founder constraints belong in the loop, not in the operator's head · confirmed
"Cannot relocate" invalidated the top-ranked opportunity after full research had been done on it. It
is a stable fact that should have screened the top-ranked opportunity out in the first thirty
seconds.
Candidate fix: a persistent constraints block in the fact sheet — relocation, geography, sector
exclusions, instrument preferences — evaluated as the first gate of intake.

### L13 — "Passed" is doing two jobs · FIXED (session 2)
Marked one record `passed` after ruling it out on eligibility. But `passed` reads as *the investor
passed on us*, which is not what happened — we screened them out before any contact. The ledger
cannot currently distinguish "they said no" from "we decided not to apply," and those mean opposite
things when reviewing a pipeline later.
Candidate fix: add a `screened-out` status distinct from `passed`/`declined`.

## Session 2 — 2026-09-05 · building the loop

Built L4, L7 and L13. Two further faults surfaced only once real data went through the new code —
neither was visible from reading the pilot's notes.

### L14 — An update was silently destroying data · FIXED, was a live bug
`fold()` took the newest `investor` line wholesale, so a partial update replaced the record rather
than amending it. `pia investor --id <id> --firm ... --status passed` — run for real in
session 1 — blanked that record's contact, check size and source. The lines were still in the file;
the folded view simply stopped showing them. Nothing errored, and the loss was invisible until
someone went looking. Adding four more fields would have quadrupled the blast radius.
Fixed: later lines now merge onto earlier ones field by field, and `--status` omitted leaves the
existing status alone rather than resetting it to `cold`. Regression test covers both. The four real
records were re-logged to restore what had been dropped.

### L15 — Deadlines are not always day-precise · FIXED
One accelerator publishes "applications close in February 2027" with no day. A `YYYY-MM-DD`-only field forces
whoever logs it to invent one, which is exactly the kind of quiet fabrication the fact-sheet rule
exists to prevent. The field now takes `YYYY-MM` too.

### L16 — Second-granular timestamps tie, and ties were sorting wrong · FIXED
`pia show` built its history by concatenating touches and notes and sorting on timestamp. Timestamps
are second-precision, so a note and a touch logged in the same second tie — and the sort then put
every touch ahead of every note regardless of write order. A skill logging a note then a touch would
display them reversed. Now built from file order, which *is* write order, so a stable sort keeps
same-second entries in the order they actually happened.

### Still open for the next pass
L1 (bootstrap), L2 (intake path), L6 (verify-at-source as a mandatory step), L8 (eligibility gate
before research), L12 (constraints evaluated first) — items 3, 5 and 6 of the plan.
L3/L9 (fact sheet) is partly addressed: `ledger/FACT-SHEET.md` exists and is dated, but nothing
enforces its freshness yet, and nothing can refresh it automatically — see the SPEC note on why that
is deliberate rather than missing.

## Session 3 — 2026-09-05 · first outbound sourcing pass

First pass that went looking for counterparties instead of reacting to ones that arrived. Nine
records logged, all verified at source. Five new faults, none of them visible before real sourcing.

### L17 — Category-level research has nowhere to live · open
The most decision-relevant finding of the pass was about the *sector*, not any one counterparty:
published funding volume for the category, the specific objections investors raise, and which of
them the product can and cannot answer today. Every `note` record hangs off an investor id, so this
had to go in a loose file the CLI does not know about. It applies to all nine records equally and
will be re-derived by whoever forgets it exists.
Candidate fix: a `category` or `market` note kind with no investor id, surfaced by `pia pipeline`.

### L18 — `deadline` has three states and reality has four · open
Blank means nobody checked, `rolling` means checked and there is no date, `YYYY-MM(-DD)` means a
date. One accelerator is none of those: it runs in cycles, applications are currently **closed**, and
the reopen date is explicitly unannounced. `rolling` would be a lie, a date would be fabrication, and
blank — the only honest option left — reads as "nobody checked" when in fact somebody checked
carefully. The record now carries the truth in prose where nothing can query it.
Candidate fix: a `closed-reopens-tba` sentinel, or split "was this checked" from "what did it say."

### L19 — Verification is per-field, not per-record · open, sharpens L6
L6 said verify at source. This pass found the harder version: counterparty sites routinely omit the
deciding terms. Two of nine publish no cheque size, no stage and no submission route on their own
site at all. Aggregators fill that vacuum, and their numbers are not reliable — for one fund the
aggregator figure and the fund's own published cheque size differ by roughly **6x**. Same failure
shape as L10, except the unreliable memory belongs to a third-party website.
So a record is not "verified" or "unverified" as a whole. It is verified field by field, and the
distinction has to survive into the draft — the notes carry explicit "NOT confirmed on their own
site" markers, but only because the writer remembered to add them.
Candidate fix: per-field provenance, or at minimum a required `--unverified` list on each record so
drafting can refuse to state a number that never had a first-party source.

### L20 — The founder constraint gate is not binary · open, refines L12
L12 said constraints belong in the loop. This pass shows the naive version over-screens. "Cannot
relocate" correctly killed an accelerator with a long-term relocation-and-build-a-team clause. It
does **not** kill a three-week in-person residency in the founder's own country — that is travel,
which the same constraint explicitly permits. A gate matching on the word "relocate" would have
thrown away a live, well-matched opportunity.
Candidate fix: the constraint block needs a threshold, not a keyword — "in-person commitments up to N
weeks are acceptable; permanent presence is not" — and the gate has to read the actual obligation.

### L21 — Sourcing beats inbound by a wide margin, and the ratio is the evidence · confirmed
Reactive intake (session 1): four opportunities off LinkedIn, **zero** survived screening. Outbound
sourcing (this session): nine counterparties, **eight** immediately actionable and the ninth eligible
but between cycles. Same screening rigour, same eligibility gates, opposite yield. L11 still holds —
a well-evidenced "no" is a real output — but a channel that produces only "no" is a bad channel.
Candidate fix: none needed; this is a strategy finding. Source deliberately, treat inbound as noise
until proven otherwise.

### L22 — The fact sheet is traction-shaped when it needs to be objection-shaped · open
The category research produced a list of the specific objections this sector gets asked. Two of them
— paid conversion rate, and the gender split of the user base — have no answer anywhere in the fact
sheet, and both are single queries against the production database. The fact sheet was built by
asking "what do we have?" when the useful question is "what will we be asked?"
Candidate fix: derive the fact sheet's required fields from the category research, and have drafting
refuse on a missing objection-answer the same way it refuses on a stale date.

### Still open after this pass
L1 (bootstrap), L2 (intake path), L6/L19 (verification, now per-field), L8 (eligibility gate),
L12/L20 (constraints as thresholds), plus L17, L18, L21, L22 above.
The institutional half of the pipeline now exists. The angel/syndicate half does not, and the
category research argues it may be the half that actually closes — that is the next sourcing pass.

---

## Session 4 — 2026-09-05 · the angel/syndicate sourcing pass

The pass session 3 said was next. Seven counterparties sourced, five verified at source, one
verified only partially, one not reachable at all. The interesting faults this time are about what
happens when verification *cannot* succeed, and about a number that was destroyed in transit.

### L23 — The CLI destroyed a figure in transit and said nothing · FIXED (session 4)
A research note containing a dollar amount was written through the shell. The `$` and the digits
immediately after it were read as a shell variable, expanded to nothing, and the note landed in the
ledger with the figure silently deleted — a sentence describing a fund's size that no longer
contained the size. `pia` never saw the number, so nothing could have warned about it. It was caught
by reading the tool's own echo of what it had stored, and corrected with a follow-up note.

Everything about this is the wrong shape. The global rule is that a number in a draft must trace to
a real source; here the number *had* a source and was lost anyway, between the operator and the
store. A shell is a lossy channel for free text, and every note in this ledger goes through one.

**Half the original candidate fix was wrong, and the error is worth keeping.** It proposed refusing
"text containing an unexpanded-looking `$`". That is backwards. Once the shell has eaten `$55`, no
`$` remains — the damage is invisible to any inspection of the string that arrives. A surviving
`$foo` means expansion did *not* happen, which is the safe case. The check would have flagged every
safe input and caught no real corruption: a check that verifies a proxy and reports success, which
is the exact failure this log recorded once already. **You cannot detect this after the fact. You
can only stop using the channel, and make what did arrive checkable.**

**What shipped (session 4):**
- Every free-text field now has a `-file` twin — `pia note --summary-file`, `--next-steps-file`,
  `pia touch --summary-file` / `--note-file`, `pia investor --note-file` — reading the body from a
  file, or from stdin as `-`. The file contents never pass through the shell. The inline forms
  remain for short bodies, and each pair is mutually exclusive so it is never ambiguous which was
  meant. A missing file and an empty body are both refused rather than silently stored as "".
- Every write prints an integrity line: `stored 412 chars · 3 figures: 500, 2, 55`. Printing the
  body back was never enough — scanning a paragraph for a figure that is no longer in it is the
  check that passes without looking. A count and an ordered list of figures can be compared against
  the source at a glance, and this works whichever input path was used, so an inline `--summary`
  that *does* get mangled now shows a short figure list instead of nothing at all.
- `--check-size`'s own help text was `e.g. $25k-100k`, a bare `$` in the field most likely to hold a
  currency figure. The documentation was demonstrating the fault. It now shows the value
  single-quoted and says why.
- Both skills and the README now instruct the file form for anything carrying a figure, and tell the
  reader to actually read the integrity line back.
- `tests/test_cli.py` is new — the repo had no CLI tests at all. 17 cases covering the file and
  stdin paths, the either/or contract, refusal of missing and empty bodies, and the integrity echo.

**Not fixed, and it cannot be:** an inline `--summary` typed in double quotes still loses the
figure, because the loss happens before the process starts. The integrity echo makes it *visible*;
only using the file form makes it *impossible*.

### L24 — "Verify at source" has no answer for a source that refuses to be read · open, extends L19
One counterparty's own site could not be reached. Not slow, not moved — actively blocked: a 403 to a
direct fetch, and a full bot-protection interstitial to a real browser session. Two independent
routes, same wall. So there is a third state that neither L6 nor L19 anticipated. L19 split records
into verified and unverified *fields*; this is a field that cannot be verified by this loop at all,
however diligent it is, and the distinction matters because "nobody checked yet" invites a retry
while "the door is locked" needs a different plan entirely — a human opening the page by hand.

The record now carries the truth in prose, marked as a lead rather than a counterparty, with an
explicit instruction not to draft from it. That works only because the writer chose to write it.
Nothing in the schema distinguishes it from a record somebody simply has not got to yet.
Candidate fix: a per-record `verification: verified | pending | blocked` state, where `blocked`
carries the reason and makes drafting refuse outright.

Related, and the same shape from the other direction: three counterparty sites in this pass render
their own headline totals as literal zeros or `$0 Mn+` placeholders. The page loads, returns 200,
and publishes a number that is not a number. A fetch that succeeds is not a field that verified.

### L25 — A counterparty's name and URL are fields, and they go stale like any other · open
One counterparty has rebranded. Its old domain 301s to the new one, the old founder-facing path 404s
under the new brand, and every aggregator consulted still cites the old name and the dead URL. The
live page was found only by opening the new homepage and looking for the founder link.

The loop had been treating identity as the one thing you can rely on — the stable handle you verify
*other* facts against. It is not. If the sourcing had stopped at the 404, the honest conclusion would
have been "this counterparty publishes nothing for founders", which is the exact opposite of true:
the page it does publish is the most specific in the whole pass.
Candidate fix: on any 404 or redirect from a published source URL, re-derive the counterparty's
current identity before recording an absence of information. An absence found at the wrong address
is not evidence.

### L26 — The pipeline models records as independent, and this pass proved they are not · open
Every record in the ledger sits at its own status, and `pia pipeline` groups by status. That model
quietly assumes each counterparty is a separate shot, playable in any order.

This pass found a hard dependency between two classes of counterparty: one class states in its own
FAQ that deals on its platform normally require a lead investor, and offers to help find one for
advisory equity or carry. In plain terms — that venue is not somewhere you go *instead of* getting a
first backer; it is the machinery for filling in the rest of a round once somebody has gone first and
set the terms. Approaching it before there is a lead produces a listing that nobody anchors. The
ledger cannot express "this one is only playable after that one", so the ordering exists only in a
loose research file and in whoever last read it.
Candidate fix: an optional `depends-on` or `sequence-after` field, or at minimum a status that means
"eligible but not yet playable", so `pia pipeline` stops presenting a blocked record as actionable.

### L27 — The missing fact-sheet fields stopped being a drafting weakness and became a gate · open, escalates L22
L22 observed that the fact sheet answers "what do we have?" instead of "what will we be asked?", and
listed paid conversion and gender split as unanswered objections. This pass changes the severity.
The single best-fit counterparty found so far — the only one anywhere in the pipeline that has
already funded a company in this exact category — publishes an eligibility gate written as
"early revenue stage". Revenue is one of the fields the fact sheet does not have.

So the gap no longer just weakens a draft. It decides whether an application is even admissible, and
it is blocking the highest-value record in the ledger. A missing objection-answer is a soft cost; a
missing eligibility-answer is a hard stop, and the fact sheet does not distinguish between them.
Candidate fix: mark fact-sheet fields as objection-relevant or eligibility-relevant, and have the
research skill refuse to rank a counterparty as top-priority while an eligibility-relevant field it
gates on is `UNKNOWN`.

### L28 — Second sourcing pass, same yield ratio · confirmed, strengthens L21
Session 3 recorded nine sourced counterparties against zero surviving inbound ones. This pass adds
seven more, six of them actionable and one blocked on access rather than on fit. Two passes, sixteen
sourced counterparties, one screened out on reachability and none on eligibility — against four
inbound opportunities of which none survived. L21 was a single observation; it is now a pattern.

### Still open after this pass
L1 (bootstrap), L2 (intake path), L6/L19/L24 (verification: per-field, and now sometimes impossible),
L8 (eligibility gate), L12/L20 (constraints as thresholds), L17 (category notes have no home — a
second such file was written this pass, so this is now two loose files the CLI cannot see), L18,
L22/L27 (fact sheet shape, now blocking), plus L25 and L26 above.

L23 was fixed in the same session it was found — see its entry above for what shipped and for the
half of its own candidate fix that turned out to be backwards.

Both halves of the pipeline now exist. The binding constraint is no longer sourcing — it is that the
best-fit counterparty found so far cannot be approached until the founder supplies the Round block
and a revenue figure, and neither is something this loop can go and find.
