# pdc-investor-agent — Spec

**Status: v1, in use.** Ledger CLI (`pia intake` / `investor` / `screen` / `touch` / `note` /
`show` / `pipeline` / `stats` / `sheet`) is built and tested. Four skills (`opportunity-intake`,
`investor-research`, `investor-outreach`, `pipeline-review`) are written. Pipeline state is read
through an Apple Numbers mirror the CLI keeps in step. First real run happened 2026-09-05: four LinkedIn-sourced
opportunities researched, all four screened out or blocked, nothing sent. The friction that run
exposed is logged in `PILOT-LOG.md` and is what the schema below was changed to fix.

## Problem framing

Pocket Dating Coach (Riteangle) needs a fundraise pipeline: investors to research, outreach to send,
meetings to track, and a way to know who's stalled without relying on memory or a scattered notes doc.
This repo is the same shape as `pdc-ad-management-agent`, `job-hunt-agent`, and
`pdc-store-release-ops`: the reasoning (research, drafting, judgment calls) happens live in whatever
Claude Code session runs one of the skills in `.claude/skills/`; this repo only persists the result
through a deterministic CLI.

## Locked decisions

1. **No Anthropic API key, anywhere, ever, in this repo.** Same rule as every other zero-API agent in
   this portfolio (`pdc-ad-management-agent/SPEC.md` decision 1, `job-hunt-agent`). Every mode here is
   a skill; the CLI never imports or calls an Anthropic client.

2. **The ledger is gitignored — genuinely absent from git, not just locally private.** This is
   stricter than `pdc-store-release-ops` (whose ledger holds no PII and is committed) and matches
   `finance-controls-agent`'s `DPL Finance/` and `job-hunt-agent`'s `Career hacking/`: investor names,
   contacts, check sizes, deal terms, and research notes are business-sensitive and personally
   identifying, and this repo is **public** on GitHub. `ledger/` is listed in `.gitignore` from the
   first commit and must stay that way — never add a `-f` force-add, never commit a seed/sample ledger
   with real names into this repo. If sample data is ever needed for a test fixture, it must be
   obviously fictional (see `tests/test_ledger.py` — `"acme-vc"` / `"Acme Ventures"`, never a real fund).

3. **Draft and record, never send, never move money.** This repo's skills research investors and draft
   outreach copy. They never send an email, post a LinkedIn message, or take any outbound action on the
   user's behalf — the human sends it, then the touch gets logged after the fact. Likewise, once an
   investor reaches `committed`, the actual legal paperwork, wire transfer, or cap-table update happens
   entirely outside this repo — this is a relationship tracker, not a deal-execution or payments system.
   Same category of boundary as `pdc-store-release-ops/SPEC.md` decision 3 ("read and record, never
   act") and `finance-controls-agent`'s "no write path to any financial system."

4. **No stored credentials of any kind.** No email/LinkedIn API tokens, no CRM API keys. Outreach is
   drafted here and sent by the human from their own authenticated session (email client, LinkedIn),
   the same pattern `pdc-store-release-ops` decision 2 uses for console access — a human stays in the
   loop for every outward action.

5. **Tech stack: Python (`uv`/`hatchling`), matching the rest of the portfolio.** Same conventions as
   `pdc-ad-management-agent`, `job-hunt-agent`, `pdc-store-release-ops` — one less thing to
   context-switch on.

6. **Repo is public; the data inside it is not.** The user explicitly chose public visibility to match
   `pocket-dating-coach` and `pdc-ad-management-agent`. That makes decision 2 load-bearing, not
   optional — nothing that identifies a real investor, a real check size, or real deal terms may ever
   land in a committed file. If this ever needs to change (e.g. a seed/backup export), it should be a
   deliberate, explicit decision by the user, not an incidental commit.

## Ledger shape

Three record kinds, all appended to `ledger/records.jsonl` (one JSON object per line — append-only,
diffable, mergeable across concurrent sessions without lock contention). **This file never enters
git** (decision 2).

- **`investor`** — an upsert-style record: id, firm, contact, entity kind, stage focus, check size,
  source (how found), source url (where the terms were verified), submission (how an approach is
  actually made), deadline, status, free-text note.

  **Entity kind** (`fund` / `angel` / `accelerator` / `programme` / `grant` / `intermediary`) exists
  because half a fundraise pipeline is not a fund, and the terms and failure modes differ per kind —
  an accelerator has eligibility criteria and a cohort deadline; an intermediary has a fee structure
  worth establishing before a deck moves. They stay one record kind rather than two because `touch`
  and `note` already reference an investor id, and a parallel kind would fork that reference.

  **Status** is `cold` / `contacted` / `meeting` / `diligence` / `committed` / `passed` /
  `screened-out` / `declined`. `passed` and `screened-out` are deliberately distinct: `passed` is
  *they* said no after contact, `screened-out` is *we* ruled them out before contacting anyone.
  Collapsing them loses the whole story when the pipeline is reviewed months later.

  **Deadline** is `YYYY-MM-DD`, `YYYY-MM` (programmes routinely publish "closes February 2027" with
  no day, and forcing a day means inventing one), or the literal `rolling` — recorded explicitly,
  because blank means nobody checked and `rolling` means somebody checked and there is no date.

  Folds per id, **merging later lines onto earlier ones field by field**. A later line is a partial
  update, not a replacement: `pia investor --id x --firm F --status passed` leaves the contact and
  source an earlier line established. Omitting `--status` leaves the existing status alone. Every
  prior line stays in the file regardless.
- **`touch`** — an append-only outreach event: investor id, channel (email/linkedin/warm-intro/event/
  call/other), direction (outbound/inbound), summary. Never folded — every touch stays in the history,
  which is what lets `pia pipeline` show "last touch N days ago."
- **`note`** — an append-only research or meeting note: investor id, note kind (research/meeting),
  summary, next steps. Never folded, same reasoning as `touch`.

- **`sighting`** (a `note` kind) — what a source *claimed*, recorded before anyone checked it.
  Written by `pia intake`, which is the entry point for a screenshot. It is deliberately not
  `research`: `research` means somebody went and verified something.

  This is the schema answering L6/L19. A cheque size seen in a LinkedIn post and one read off the
  fund's own site are different kinds of fact, and if both land in `check_size` nothing downstream
  can separate them. So `pia intake` carries identity and provenance only — it has no
  `--check-size`, `--deadline`, `--stage-focus` or `--submission` flags at all, and the claims go
  into the sighting note as prose. The verified fields get filled in later, by `pia investor`,
  once each has a first-party source.

- **`eligibility`** (a field on `investor`, plus a `screening` note kind) — `unscreened` (the
  implicit default) / `eligible` / `ineligible`, alongside the criterion that decided it.

  A separate field rather than another `status` value, deliberately. Status tracks how far a
  relationship has progressed; eligibility is a fact about the counterparty that does not change as
  the relationship moves. Folding it into status would repeat the L7 mistake — one field carrying
  two meanings compares across records for neither.

  Written only by `pia screen`, which requires both a criterion and a reason. A verdict nobody can
  check is the same problem as no verdict in a new field. `ineligible` sets `status` to
  `screened-out` in the same call, because they are one event.

  `unscreened` cannot be asserted as a verdict — it is the absence of one. Being able to write it
  would let a record look screened while recording that nothing was found.

`pia pipeline` folds this into "who's where right now, and when were they last touched" without
requiring anyone to remember it by hand, and flags any record nobody has screened that is not
already out of play.

## The eligibility gate, and the limit of it

`cold` was carrying two meanings: "checked their published criteria, we qualify" and "nobody has
looked". `investor-outreach` drafts from the `cold` list, so the loop could produce a careful,
specific approach to a counterparty that excludes consumer dating by published policy, with every
part of the system appearing to work. Three of the pilot's four opportunities died on published
eligibility (`PILOT-LOG.md` L8), which is how often this matters.

`pia touch --direction outbound` refuses on a record that is not `eligible`. `--force-unscreened`
overrides it and records `forced_past_eligibility` on the touch, so a forced touch stays
distinguishable from a screened one — an override that leaves no trace is indistinguishable from
the gate never having existed.

**What this does not do.** It does not prevent drafting or sending. Drafting happens in a session;
sending happens in the human's own email or LinkedIn (decision 3). Nothing in this CLI sits upstream
of either, so the gate fires *after* the irreversible act, at the first moment the tooling is
involved at all. It is a smoke alarm, not a lock. What it genuinely changes is that an unchecked
record can no longer present itself as ready: `pia show` states the verdict under the status on
every read, `pia pipeline` marks it inline, and the sheet carries it as a column. Calling this
"the eligibility gate is enforced" would be the `commons doctor` failure — a check that verifies a
proxy and reports success. See `PILOT-LOG.md` L31.

## The Numbers mirror

`ledger/PDC Investor Pipeline 2026.numbers` is a rendering of the ledger, created by
`pia sheet --init` and refreshed by every subsequent `pia` write. It is how the user actually
consumes pipeline state, in the same way the Career Hacking Tracker is consumed in `job-hunt-agent`.

**One-way, ledger wins.** The mirror is written and never read back, so the sheet cannot become a
second source of truth that quietly disagrees with `records.jsonl`. A hand-edited cell is not an
error anything can detect; it is overwritten on the next write.

Rows are matched by `id` and columns by header name, so the user's sort and column order survive a
sync. `job-hunt-agent`'s equivalent has to synthesise a row identity from `Date + Company + Role`
and count repeats because a job ledger has no stable key; every record here has one, so two
records can never collapse into a single row.

The mirror is best-effort by construction: the JSONL append has already succeeded before the mirror
runs, and a sheet locked open in Numbers must not turn a successful ledger write into a failed
command. It warns; `pia sheet` catches up afterwards.

It lives inside `ledger/`, so decision 2 covers it. It holds the same investor names, contacts and
deal terms in a more readable shape, which makes it *more* sensitive than the JSONL, not less.

This introduces the package's only dependency, `numbers-parser` (the same one `job-hunt-agent`
uses). It is a plain dependency rather than an optional extra on purpose: an extra that is not
installed would make the mirror stop updating silently, and a sheet that has quietly gone stale is
worse than no sheet — that is the `commons doctor` failure shape, a check that reports success
without verifying anything. Nothing about decisions 1 and 4 changes: no Anthropic client, no
credentials.

## Not built yet

- No deadline awareness in `pia pipeline` — the field is stored but nothing flags a cohort close
  approaching, and `screened-out` records are still shown rather than hidden by default.
- **No automated traction refresh, and this one is deliberate.** The obvious feature is a command
  that pulls live product metrics into an application fact sheet. It would require a Supabase
  credential in this repo, which decision 4 forbids — so the fact sheet stays a dated file written
  by a session that already has access, and drafting refuses to run against a stale one. Convenience
  does not get to quietly delete the boundary that makes a public repo safe.
- No scheduled/unattended run of `pipeline-review` — same reasoning as `pdc-store-release-ops`
  decision 9: prove the loop by hand first, promote to a scheduled task deliberately and later.
