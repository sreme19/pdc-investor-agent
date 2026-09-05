"""pia — CLI entrypoint for the pdc-investor-agent ledger.

No network calls, no credentials, no Anthropic API key, no email-sending. This CLI only ever reads
and appends to ledger/records.jsonl (gitignored — see SPEC.md decision 2). All the actual research
judgment and outreach drafting happens in the Claude Code session running one of the skills in
.claude/skills/; this CLI just persists the result deterministically.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from pdc_investor_agent.ledger import (
    VALID_ENTITY_KINDS,
    VALID_STATUSES,
    VALID_SUBMISSIONS,
    Ledger,
    LedgerError,
)

# Display order for `pipeline`: the live pipeline in the order it actually progresses, then the two
# ways a record dies. `screened-out` sits last because it is the pile you deliberately stop looking at.
STATUS_ORDER = [
    "cold",
    "contacted",
    "meeting",
    "diligence",
    "committed",
    "passed",
    "declined",
    "screened-out",
]


def _age_days(ts: str) -> int:
    then = datetime.fromisoformat(ts)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).days


def _status_order() -> list[str]:
    """Declared order first, then anything valid that isn't listed, so nothing goes invisible."""
    return STATUS_ORDER + sorted(VALID_STATUSES - set(STATUS_ORDER))


def cmd_investor(args: argparse.Namespace) -> int:
    ledger = Ledger()
    record = ledger.investor(
        args.id,
        args.firm,
        contact=args.contact or "",
        entity_kind=args.kind or "",
        stage_focus=args.stage_focus or "",
        check_size=args.check_size or "",
        source=args.source or "",
        source_url=args.source_url or "",
        submission=args.submission or "",
        deadline=args.deadline or "",
        status=args.status or "",
        note=args.note or "",
    )
    merged = ledger.latest_investor(args.id) or record
    print(f"logged investor [{merged['id']}] {merged['firm']} — status {merged.get('status') or 'cold'}")
    return 0


def cmd_touch(args: argparse.Namespace) -> int:
    ledger = Ledger()
    record = ledger.touch(
        args.investor, args.channel, args.direction, args.summary, note=args.note or ""
    )
    print(f"logged {record['direction']} touch [{record['investor_id']}] via {record['channel']}: {record['summary']}")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    ledger = Ledger()
    record = ledger.note(
        args.investor, args.kind, args.summary, next_steps=args.next_steps or ""
    )
    print(f"logged {record['note_kind']} note [{record['investor_id']}]: {record['summary']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    ledger = Ledger()
    detail = ledger.show(args.id)
    if detail is None:
        print(f"error: no investor with id {args.id!r}", file=sys.stderr)
        return 1
    inv = detail["investor"]

    headline = f"[{inv['id']}] {inv['firm']}"
    if inv.get("entity_kind"):
        headline += f"  ({inv['entity_kind']})"
    print(headline)
    print(f"  status: {inv.get('status') or 'cold'}")
    for label, key in (
        ("contact", "contact"),
        ("stage focus", "stage_focus"),
        ("check size", "check_size"),
        ("submission", "submission"),
        ("deadline", "deadline"),
        ("source", "source"),
        ("source url", "source_url"),
        ("note", "note"),
    ):
        if inv.get(key):
            print(f"  {label}: {inv[key]}")

    if not detail["history"]:
        print("\n  (no notes or touches logged)")
        return 0

    print(f"\n  history ({len(detail['history'])} entries, oldest first):")
    for entry in detail["history"]:
        stamp = entry["ts"][:10]
        age = _age_days(entry["ts"])
        if entry["kind"] == "touch":
            head = f"{entry['direction']} touch via {entry['channel']}"
        else:
            head = f"{entry['note_kind']} note"
        print(f"\n  · {stamp} ({age}d ago) — {head}")
        print(f"      {entry['summary']}")
        if entry.get("next_steps"):
            print(f"      next: {entry['next_steps']}")
        if entry.get("note"):
            print(f"      note: {entry['note']}")
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    ledger = Ledger()
    p = ledger.pipeline()
    if not p["by_status"]:
        print("(no investors logged yet)")
        return 0
    for status in _status_order():
        group = p["by_status"].get(status)
        if not group:
            continue
        print(f"== {status} ({len(group)}) ==")
        for investor in group:
            last_touch = p["last_touch_by_investor"].get(investor["id"])
            touch_str = f"last touch {_age_days(last_touch['ts'])}d ago via {last_touch['channel']}" if last_touch else "no touches logged"
            label = investor["firm"]
            if investor.get("entity_kind"):
                label += f" ({investor['entity_kind']})"
            print(f"  [{investor['id']}] {label} — {touch_str}")
            if investor.get("deadline"):
                print(f"      deadline: {investor['deadline']}")
            if investor.get("note"):
                print(f"      note: {investor['note']}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    ledger = Ledger()
    records = ledger.read_all()
    kinds = {}
    for r in records:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"total records: {len(records)}")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pia")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "investor",
        help="Add or update an investor record (also: accelerators, programmes, grants, intermediaries)",
    )
    p.add_argument("--id", required=True, help="stable slug, e.g. acme-ventures")
    p.add_argument("--firm", required=True)
    p.add_argument("--contact", help="name <email>")
    p.add_argument(
        "--kind",
        choices=sorted(VALID_ENTITY_KINDS),
        help="what this counterparty is; half a fundraise pipeline is not a fund",
    )
    p.add_argument("--stage-focus", help="e.g. pre-seed, seed, series-a")
    p.add_argument("--check-size", help="e.g. $25k-100k")
    p.add_argument("--source", help="how this investor was found / who referred them")
    p.add_argument("--source-url", help="where the terms were verified — the counterparty's own page")
    p.add_argument(
        "--submission",
        choices=sorted(VALID_SUBMISSIONS),
        help="how an approach is actually made (decides what gets drafted)",
    )
    p.add_argument("--deadline", help="YYYY-MM-DD, YYYY-MM when only a month was published, or 'rolling' when there is none")
    p.add_argument(
        "--status",
        choices=sorted(VALID_STATUSES),
        help="omit to leave the existing status alone; a record that never had one reads as 'cold'",
    )
    p.add_argument("--note")
    p.set_defaults(func=cmd_investor)

    p = sub.add_parser("touch", help="Log an outreach touch (email, LinkedIn, intro, call)")
    p.add_argument("--investor", required=True, help="investor id")
    p.add_argument("--channel", required=True, choices=["email", "linkedin", "warm-intro", "event", "call", "other"])
    p.add_argument("--direction", required=True, choices=["outbound", "inbound"])
    p.add_argument("--summary", required=True)
    p.add_argument("--note")
    p.set_defaults(func=cmd_touch)

    p = sub.add_parser("note", help="Log a research or meeting note")
    p.add_argument("--investor", required=True, help="investor id")
    p.add_argument("--kind", required=True, choices=["research", "meeting"])
    p.add_argument("--summary", required=True)
    p.add_argument("--next-steps")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("show", help="One investor's whole file: record, notes and touches in order")
    p.add_argument("id", help="investor id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("pipeline", help="Show every investor grouped by status")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("stats", help="Record counts by kind")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
