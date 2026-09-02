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
pia investor --id acme-vc --firm "Acme Ventures" --stage-focus seed --check-size "$25k-100k" \
  --source "cold list" --status cold
pia pipeline
```

## Commands

| Command | What it does | When you use it |
|---|---|---|
| `pia investor` | Adds or updates an investor record: firm, contact, stage focus, check size, source, status. Re-run with the same `--id` to move them through the pipeline. | When a new investor enters the pipeline, or their status/contact info changes. |
| `pia touch` | Logs one outreach event: channel, direction, summary. | Every time an email/LinkedIn message/call actually happens, in either direction. |
| `pia note` | Logs a research or meeting note, with optional next steps. | After researching a fund, or after a call/meeting. |
| `pia pipeline` | Shows every investor grouped by status, with the age of their last touch. | Before a follow-up pass, or any time you want to know where things stand. |
| `pia stats` | One-line record counts by kind. | Quick sanity check. |

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
- `ledger/` is gitignored from the first commit (`SPEC.md` decision 2) — investor names, contacts,
  check sizes, and deal terms must never be pushed to GitHub.
