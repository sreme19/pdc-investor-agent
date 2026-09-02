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

from pdc_investor_agent.ledger import Ledger, LedgerError


def _age_days(ts: str) -> int:
    then = datetime.fromisoformat(ts)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).days


def cmd_investor(args: argparse.Namespace) -> int:
    ledger = Ledger()
    record = ledger.investor(
        args.id,
        args.firm,
        contact=args.contact or "",
        stage_focus=args.stage_focus or "",
        check_size=args.check_size or "",
        source=args.source or "",
        status=args.status,
        note=args.note or "",
    )
    print(f"logged investor [{record['id']}] {record['firm']} — status {record['status']}")
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


def cmd_pipeline(args: argparse.Namespace) -> int:
    ledger = Ledger()
    p = ledger.pipeline()
    if not p["by_status"]:
        print("(no investors logged yet)")
        return 0
    order = ["cold", "contacted", "meeting", "diligence", "committed", "passed", "declined"]
    for status in order:
        group = p["by_status"].get(status)
        if not group:
            continue
        print(f"== {status} ({len(group)}) ==")
        for investor in group:
            last_touch = p["last_touch_by_investor"].get(investor["id"])
            touch_str = f"last touch {_age_days(last_touch['ts'])}d ago via {last_touch['channel']}" if last_touch else "no touches logged"
            print(f"  [{investor['id']}] {investor['firm']} — {touch_str}")
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

    p = sub.add_parser("investor", help="Add or update an investor record")
    p.add_argument("--id", required=True, help="stable slug, e.g. acme-ventures")
    p.add_argument("--firm", required=True)
    p.add_argument("--contact", help="name <email>")
    p.add_argument("--stage-focus", help="e.g. pre-seed, seed, series-a")
    p.add_argument("--check-size", help="e.g. $25k-100k")
    p.add_argument("--source", help="how this investor was found / who referred them")
    p.add_argument(
        "--status",
        default="cold",
        choices=["cold", "contacted", "meeting", "diligence", "committed", "passed", "declined"],
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
