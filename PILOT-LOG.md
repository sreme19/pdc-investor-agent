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
