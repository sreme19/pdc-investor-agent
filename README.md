# pdc-investor-agent

Zero-API ledger CLI for investor outreach, research, and relationship tracking, for the Pocket Dating
Coach (Riteangle) fundraise. Investor records, research notes, and outreach history live as an
append-only ledger in a gitignored local folder; the reasoning happens in a Claude Code session
through the skills in `.claude/skills/`; this CLI only reads and writes the ledger, deterministically.

Same shape as `pdc-ad-management-agent`, `job-hunt-agent`, and `pdc-store-release-ops`: no Anthropic
API key anywhere in the package, and a hard boundary against performing the irreversible outward
action (sending a message, moving money) itself.

See `SPEC.md` for the design and its locked decisions — in particular decision 2: **the ledger is
gitignored and must never be committed.** This repo is public; the investor data inside it is not.

## Install

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

## First run

```bash
pia investor --id acme-vc --firm "Acme Ventures" --kind fund --stage-focus seed \
  --check-size '$25k-100k' --source "cold list" --submission email --status cold
pia pipeline
pia show acme-vc

# Create the Apple Numbers mirror once. Every pia write keeps it current from then on.
pia sheet --init
```

## Commands

| Command | What it does | When you use it |
|---|---|---|
| `pia intake` | Logs a counterparty somebody just saw, with what the source *claimed*, as a `sighting`. Identity and where-it-was-seen only. | The moment a screenshot or a post shows up, before anything about it has been checked. |
| `pia investor` | Adds or updates a record: firm, contact, entity kind, stage focus, check size, source, source url, submission route, deadline, status. Re-run with the same `--id` to move them through the pipeline — later lines merge onto earlier ones field by field, so a status change never blanks the contact. | When a new investor or programme enters the pipeline, or their status/details change. |
| `pia screen` | Records an eligibility verdict against the counterparty's own published criteria, with the criterion and the evidence. `ineligible` also sets `screened-out`. | After the eligibility gate, before any outreach. An outbound touch is refused until this has been run. |
| `pia sheet` | Refreshes the Apple Numbers mirror. `--init` creates it the first time. | Once at setup; after that only to catch up a sheet that was open in Numbers during a write. |
| `pia touch` | Logs one outreach event: channel, direction, summary. | Every time an email/LinkedIn message/call actually happens, in either direction. |
| `pia note` | Logs a research or meeting note, with optional next steps. | After researching a fund, or after a call/meeting. |
| `pia show <id>` | Prints one record's whole file: every field, plus every research note and touch in the order they happened. | Picking up an investor a previous session logged, before drafting anything. |
| `pia pipeline` | Shows every investor grouped by status, with entity kind, deadline, and the age of their last touch. | Before a follow-up pass, or any time you want to know where things stand. |
| `pia stats` | One-line record counts by kind. | Quick sanity check. |

Every free-text field (`--summary`, `--next-steps`, `--note`) has a `-file` twin — `--summary-file PATH`, or `-` for stdin — that reads the body from a file instead of the command line. **Use it for anything containing a figure.** Text typed inline passes through the shell, which expands `$55 million` to ` million` before `pia` ever runs; the figure is gone and nothing in the stored string reveals that it was ever there. A file never touches the shell. Every write also prints back the character count and each figure stored, so a number lost anywhere upstream is visible instead of silent. See `PILOT-LOG.md` L23 — this corrupted a real record before it was fixed.

### `pia intake` and why it has fewer flags than you expect

`intake` writes two lines: an investor stub carrying identity and where it was seen, and a
`sighting` note carrying what the source claimed, as prose.

It has **no** `--check-size`, `--deadline`, `--stage-focus` or `--submission`, and the omission is
the point. Those fields are for figures read off the counterparty's own page. A cheque size lifted
from a LinkedIn post and one verified at source are not the same fact, and once both are sitting in
`check_size` nothing downstream can tell them apart — not a draft, not a review, not you in three
months. Fill them in with `pia investor` once each has actually been checked.

This is not hypothetical. In the pilot one post implied an immediate deadline that the programme's
own site put five months out, and one aggregator's cheque size differed from the fund's own
published figure by roughly 6x (`PILOT-LOG.md` L6, L19).

## The eligibility gate

`cold` used to mean two different things: "we checked their published criteria and we qualify" and
"nobody has looked yet". `investor-outreach` drafts from the `cold` list, so the loop could write a
careful, specific approach to a fund that excludes consumer dating by policy — and every part of the
system would have looked like it worked.

So eligibility is its own field, separate from status, with three states: `unscreened` (the default),
`eligible`, `ineligible`. It is a separate field rather than another status value because status
tracks how far a relationship has got, and eligibility is a fact about the counterparty that does not
change as the relationship moves.

```bash
pia screen --investor acme-vc --verdict eligible \
  --criterion "seed consumer, no sector exclusion" --reason-file /tmp/why.md
```

Both the criterion and the reason are required — a verdict nobody can check is the same problem as
no verdict. `--verdict ineligible` sets `status` to `screened-out` with it, since they are one event.

**What is enforced, and what is not.** `pia touch --direction outbound` refuses on an unscreened
record. That is real, but it is a smoke alarm rather than a lock: by the time an outbound touch is
logged, the message has already been sent by hand, and nothing in a ledger sits upstream of that.
What the gate actually buys is that the mistake surfaces while the conversation is still fresh, and
that `pia show` and `pia pipeline` can no longer present an unchecked record as though it were
ready. Deciding not to draft is still a judgment call a session has to make.

## The Numbers sheet

`pia sheet --init` creates `ledger/PDC Investor Pipeline 2026.numbers`, and from then on **every
`pia` write mirrors into it automatically**. Four tabs: **Pipeline** (one row per counterparty),
**Touches & Notes** (the full history), **Research Files** (the loose markdown beside the ledger,
and which record each belongs to), and **Legend** (the status and eligibility vocabulary).

The Pipeline tab carries `Eligibility`, `Screened On` and `Criterion`, so "is this row actionable"
is answerable without leaving the row. An unscreened record shows the word `unscreened`, never a
blank — a blank cell reads as "not applicable", which is the opposite of what it means.

A column added after a sheet already exists lands at the **far right**, not in the position it
occupies in the code. That is deliberate: appending is the only way to add a column without
shuffling the layout you arranged. Drag it wherever you want it — the mirror matches columns by
header name, so it will keep following the column, not the position.

Same contract as the Career Hacking Tracker in `job-hunt-agent`: **one-way, and the ledger always
wins.** `records.jsonl` is the source of truth; the sheet is a rendering of it. Editing a cell by
hand is not an error anything can catch — the next `pia` write simply overwrites it.

Sort and reorder it however you like. Rows are matched by `ID` and columns by header name, so a
sync finds each row again wherever you moved it instead of rewriting your sort. New records land in
the first blank row.

Two things worth knowing:

- **Numbers holds a lock on an open file.** If the sheet is open when a write lands, the ledger
  write still succeeds and you get `warning: ledger written, sheet NOT updated`. Close it and run
  `pia sheet`.
- The mirror is opt-in. Until you run `--init`, `pia` never mentions it.

## Skills

- **`opportunity-intake`** — turns a pasted screenshot into a logged, screened, source-verified
  record: log the sighting first, then the eligibility gate, then verify each field at the
  counterparty's own site. Never contacts anyone, and stops short of drafting.
- **`investor-research`** — researches a named fund/angel (thesis fit, portfolio overlap, warm-intro
  path) and logs the result. Never contacts anyone.
- **`investor-outreach`** — drafts outreach copy from logged research, and logs the touch after the
  human sends it. Never sends anything itself.
- **`pipeline-review`** — summarizes the pipeline: who's stalled, who needs a follow-up, what's
  approaching a decision. Never changes a status itself.

## Boundaries enforced in code

- No Anthropic client is imported anywhere in the package.
- No credentials of any kind; no email/LinkedIn/CRM API token, no write path to any financial system.
- `pia touch` and `pia note` both require the investor to already exist — no orphan records.
- A record you screened out yourself (`screened-out`) is never conflated with one that turned you
  down (`passed`).
- No credential lives here, so the CLI cannot pull product metrics itself — see `SPEC.md` decision 4
  and the "Not built yet" note on why that stays true.
- `pia intake` cannot write a claim into a verified field — the flags do not exist.
- `pia touch --direction outbound` refuses on a record nobody has screened. `--force-unscreened`
  gets past it and is recorded on the touch, so a forced touch stays distinguishable from a
  screened one.
- `pia screen` will not accept a verdict without a criterion and a reason.
- `unscreened` cannot be asserted as a verdict — it is the absence of one.
- The Numbers mirror is written but never read back, so the sheet can never become a second source
  of truth that disagrees with the ledger.
- A mirror failure warns; it can never fail a ledger write that already succeeded.
- `ledger/` is gitignored from the first commit (`SPEC.md` decision 2) — investor names, contacts,
  check sizes, and deal terms must never be pushed to GitHub. **The Numbers sheet lives inside
  `ledger/` for exactly this reason** — it is the same data in a nicer shape, and it is covered by
  the same rule.
