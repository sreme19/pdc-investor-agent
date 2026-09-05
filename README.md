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
  --check-size "$25k-100k" --source "cold list" --submission email --status cold
pia pipeline
pia show acme-vc
```

## Commands

| Command | What it does | When you use it |
|---|---|---|
| `pia investor` | Adds or updates a record: firm, contact, entity kind, stage focus, check size, source, source url, submission route, deadline, status. Re-run with the same `--id` to move them through the pipeline — later lines merge onto earlier ones field by field, so a status change never blanks the contact. | When a new investor or programme enters the pipeline, or their status/details change. |
| `pia touch` | Logs one outreach event: channel, direction, summary. | Every time an email/LinkedIn message/call actually happens, in either direction. |
| `pia note` | Logs a research or meeting note, with optional next steps. | After researching a fund, or after a call/meeting. |
| `pia show <id>` | Prints one record's whole file: every field, plus every research note and touch in the order they happened. | Picking up an investor a previous session logged, before drafting anything. |
| `pia pipeline` | Shows every investor grouped by status, with entity kind, deadline, and the age of their last touch. | Before a follow-up pass, or any time you want to know where things stand. |
| `pia stats` | One-line record counts by kind. | Quick sanity check. |

Every free-text field (`--summary`, `--next-steps`, `--note`) has a `-file` twin — `--summary-file PATH`, or `-` for stdin — that reads the body from a file instead of the command line. **Use it for anything containing a figure.** Text typed inline passes through the shell, which expands `$55 million` to ` million` before `pia` ever runs; the figure is gone and nothing in the stored string reveals that it was ever there. A file never touches the shell. Every write also prints back the character count and each figure stored, so a number lost anywhere upstream is visible instead of silent. See `PILOT-LOG.md` L23 — this corrupted a real record before it was fixed.

## Skills

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
- `ledger/` is gitignored from the first commit (`SPEC.md` decision 2) — investor names, contacts,
  check sizes, and deal terms must never be pushed to GitHub.
