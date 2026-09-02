# pdc-investor-agent — Spec

**Status: v1 scaffold.** Ledger CLI (`pia investor` / `touch` / `note` / `pipeline` / `stats`) is
built and tested. Three skills (`investor-research`, `investor-outreach`, `pipeline-review`) are
written. Nothing here has run for real yet — no investor has been logged.

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

- **`investor`** — an upsert-style record: id, firm, contact, stage focus, check size, source (how
  found), status (`cold` / `contacted` / `meeting` / `diligence` / `committed` / `passed` /
  `declined`), free-text note. Folds to the latest line per id — re-logging with the same `--id`
  updates status/contact fields without losing history (every prior line stays in the file).
- **`touch`** — an append-only outreach event: investor id, channel (email/linkedin/warm-intro/event/
  call/other), direction (outbound/inbound), summary. Never folded — every touch stays in the history,
  which is what lets `pia pipeline` show "last touch N days ago."
- **`note`** — an append-only research or meeting note: investor id, note kind (research/meeting),
  summary, next steps. Never folded, same reasoning as `touch`.

`pia pipeline` folds this into "who's where right now, and when were they last touched" without
requiring anyone to remember it by hand.

## Not built yet

- No `pia show <id>` to print an investor's full history (research notes, touches) in one place —
  today that means re-reading raw ledger lines or asking whoever logged the note. Worth adding once
  the pipeline has enough investors that this is a real friction point.
- No scheduled/unattended run of `pipeline-review` — same reasoning as `pdc-store-release-ops`
  decision 9: prove the loop by hand first, promote to a scheduled task deliberately and later.
