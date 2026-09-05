"""pia — CLI entrypoint for the pdc-investor-agent ledger.

No network calls, no credentials, no Anthropic API key, no email-sending. This CLI only ever reads
and appends to ledger/records.jsonl (gitignored — see SPEC.md decision 2). All the actual research
judgment and outreach drafting happens in the Claude Code session running one of the skills in
.claude/skills/; this CLI just persists the result deterministically.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pdc_investor_agent.ledger import (
    CLOSED_STATUSES,
    UNSCREENED,
    VALID_ELIGIBILITY,
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


# Any run of digits, keeping decimal points and thousands separators together, so "2.5" and "1,160"
# each read as one figure rather than two. Used only for the integrity echo.
_FIGURE = re.compile(r"\d[\d,.]*")

# Beyond this many figures the echo is a wall of numbers nobody reads, so it truncates.
_MAX_ECHOED_FIGURES = 40

_stdin_consumed = False


def _read_body(path: str, flag: str) -> str:
    """Read one free-text field from a file (or stdin, as `-`) rather than from argv.

    This exists because argv is a lossy channel. Text handed to the shell in double quotes has `$`
    sequences expanded before this process ever starts, so `"a $55 million fund"` arrives as
    `"a  million fund"` — a figure deleted in transit, with nothing left in the string to detect it
    by. The file path never passes through that expansion. See PILOT-LOG.md L23.
    """
    global _stdin_consumed
    if path == "-":
        if _stdin_consumed:
            raise LedgerError(
                f"{flag}: stdin was already read by another field — only one field per command "
                "can use '-'; put the others in files"
            )
        _stdin_consumed = True
        text = sys.stdin.read()
    else:
        target = Path(path)
        if not target.exists():
            raise LedgerError(f"{flag}: no such file: {path}")
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as e:
            raise LedgerError(f"{flag}: could not read {path}: {e}") from e
    # Only trailing newlines go: leading whitespace and internal blank lines are the author's.
    text = text.rstrip("\n")
    if not text.strip():
        raise LedgerError(f"{flag}: body is empty — an empty body is a bug, not a note")
    return text


def _body(args: argparse.Namespace, dest: str) -> str:
    """The value for one free-text field, from its file form if given, else its argv form."""
    from_file = getattr(args, f"{dest}_file", None)
    if from_file is not None:
        return _read_body(from_file, "--" + dest.replace("_", "-") + "-file")
    return getattr(args, dest, None) or ""


def _figures(text: str) -> list[str]:
    return [m.group(0).rstrip(".,") for m in _FIGURE.finditer(text)]


def _integrity_line(*parts: str) -> str:
    """A checkable summary of what actually landed in the ledger.

    Printing the body back is not enough on its own — scanning a paragraph of prose for a figure
    that is no longer in it is exactly the check that reports success without verifying anything.
    The character count and the list of every figure stored can be compared against the source at a
    glance, so a number lost anywhere upstream shows up as a short list.
    """
    text = " ".join(part for part in parts if part)
    figures = _figures(text)
    head = f"  stored {len(text)} chars"
    if not figures:
        return head + " · no figures"
    shown = figures[:_MAX_ECHOED_FIGURES]
    tail = "" if len(figures) == len(shown) else f" … (+{len(figures) - len(shown)} more)"
    label = "figure" if len(figures) == 1 else "figures"
    return head + f" · {len(figures)} {label}: " + ", ".join(shown) + tail


def _age_days(ts: str) -> int:
    then = datetime.fromisoformat(ts)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).days


def _mirror_after_write(ledger) -> None:
    """Push the ledger into the Numbers sheet, if the user has created one.

    Best-effort on purpose. `records.jsonl` is the source of truth and the write has already
    landed by the time this runs; a sheet left open in Numbers must not turn a successful ledger
    write into a failed command. It warns instead, loudly enough to be worth acting on, and
    `pia sheet` catches the sheet up afterwards.

    Silent when no sheet exists: the mirror is opt-in via `pia sheet --init`, and nagging on every
    write about a file the user never asked for is how a warning gets trained out of being read.
    """
    from pdc_investor_agent.numbers_sheet import SheetError, default_sheet_path, mirror

    path = default_sheet_path(ledger.path)
    if not path.exists():
        return
    try:
        print(f"  {mirror(ledger, path)}")
    except SheetError as e:
        print(f"warning: ledger written, sheet NOT updated — {e}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - see below
        # Deliberately blind. The ledger append has already succeeded by the time this runs, and
        # the exit code is read by scripts and skills as "did the record land". Letting an
        # unforeseen fault in the mirror — a numbers-parser edge case, a bug in row building —
        # turn a successful write into a failed command would report the wrong thing about the
        # only part that matters. It degrades to a visible warning; `pia sheet` catches up after.
        print(f"warning: ledger written, sheet NOT updated — {e}", file=sys.stderr)


def _status_order() -> list[str]:
    """Declared order first, then anything valid that isn't listed, so nothing goes invisible."""
    return STATUS_ORDER + sorted(VALID_STATUSES - set(STATUS_ORDER))


def cmd_investor(args: argparse.Namespace) -> int:
    ledger = Ledger()
    note = _body(args, "note")
    check_size = args.check_size or ""
    record = ledger.investor(
        args.id,
        args.firm,
        contact=args.contact or "",
        entity_kind=args.kind or "",
        stage_focus=args.stage_focus or "",
        check_size=check_size,
        source=args.source or "",
        source_url=args.source_url or "",
        submission=args.submission or "",
        deadline=args.deadline or "",
        status=args.status or "",
        note=note,
    )
    merged = ledger.latest_investor(args.id) or record
    print(f"logged investor [{merged['id']}] {merged['firm']} — status {merged.get('status') or 'cold'}")
    # check_size is echoed because it is the field most likely to carry a currency figure, and so
    # the one most exposed to the argv expansion this echo exists to make visible.
    if check_size:
        print(f"  check size: {check_size}")
    print(_integrity_line(check_size, args.source or "", note))
    _mirror_after_write(ledger)
    return 0


def cmd_intake(args: argparse.Namespace) -> int:
    """Log a sighting: a counterparty somebody saw, before anybody has checked anything.

    Two lines land, and the split is the point. The investor line carries only identity and where
    it was seen. Everything the source *claimed* — cheque size, deadline, stage, who to write to —
    goes into a `sighting` note as prose, and none of it touches the verified fields.

    `intake` therefore has no `--check-size`, `--deadline`, `--stage-focus` or `--submission` flags,
    and that omission is the feature. Those fields are for figures read off the counterparty's own
    site; a number lifted from a LinkedIn post that lands in `check_size` is indistinguishable from
    a verified one a month later. Use `pia investor` to fill them in once each has been checked.
    See PILOT-LOG.md L2 (nothing catches a screenshot before research) and L6/L19 (posts misstate
    terms, and verification is per field).
    """
    ledger = Ledger()
    seen = _body(args, "seen")
    existing = ledger.latest_investor(args.id)

    ledger.investor(
        args.id,
        args.firm,
        entity_kind=args.kind or "",
        source=args.source,
        source_url=args.source_url or "",
        # Only on the way in. Re-running intake on a counterparty already at `contacted` must not
        # drag it back to `cold` — an omitted status leaves the existing one alone.
        status="" if existing else "cold",
    )
    ledger.note(args.id, "sighting", seen)

    verb = "updated" if existing else "logged"
    print(f"{verb} sighting [{args.id}] {args.firm}" + (f" ({args.kind})" if args.kind else ""))
    print(_integrity_line(seen, args.source, args.source_url or ""))
    if existing:
        print(f"  already in the ledger at status {existing.get('status') or 'cold'} — sighting appended")
    print("  claims recorded as a sighting; nothing verified yet")
    print("  next: eligibility gate, then verify each field at the counterparty's own site")
    _mirror_after_write(ledger)
    return 0


def cmd_sheet(args: argparse.Namespace) -> int:
    from pdc_investor_agent.numbers_sheet import (
        SheetError,
        create,
        default_sheet_path,
        mirror,
    )

    ledger = Ledger()
    path = default_sheet_path(ledger.path)
    try:
        if args.init:
            print(create(path))
        print(mirror(ledger, path))
    except SheetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"  {path}")
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    ledger = Ledger()
    reason = _body(args, "reason")
    ledger.screen(args.investor, args.verdict, args.criterion, reason)
    print(f"screened [{args.investor}] — {args.verdict}")
    print(f"  criterion: {args.criterion}")
    if args.verdict == "ineligible":
        print("  status set to screened-out (we ruled them out; they never said no)")
    else:
        print("  outbound touches are now unblocked for this record")
    print(_integrity_line(args.criterion, reason))
    _mirror_after_write(ledger)
    return 0


def cmd_touch(args: argparse.Namespace) -> int:
    ledger = Ledger()
    summary = _body(args, "summary")
    note = _body(args, "note")
    record = ledger.touch(
        args.investor,
        args.channel,
        args.direction,
        summary,
        note=note,
        force_unscreened=args.force_unscreened,
    )
    if record.get("forced_past_eligibility"):
        print(
            f"warning: logged past the eligibility gate — {args.investor} is "
            f"{record['forced_past_eligibility']}. Recorded on the touch.",
            file=sys.stderr,
        )
    print(f"logged {record['direction']} touch [{record['investor_id']}] via {record['channel']}: {record['summary']}")
    print(_integrity_line(summary, note))
    _mirror_after_write(ledger)
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    ledger = Ledger()
    summary = _body(args, "summary")
    next_steps = _body(args, "next_steps")
    record = ledger.note(args.investor, args.kind, summary, next_steps=next_steps)
    print(f"logged {record['note_kind']} note [{record['investor_id']}]: {record['summary']}")
    print(_integrity_line(summary, next_steps))
    _mirror_after_write(ledger)
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
    # Directly under status, always printed, never omitted when empty — the whole failure this
    # field exists for is an unscreened record being indistinguishable from a checked one.
    eligibility = inv.get("eligibility") or UNSCREENED
    if eligibility == "eligible":
        print("  eligibility: eligible")
    elif eligibility == "ineligible":
        print("  eligibility: INELIGIBLE — do not draft, do not approach")
    else:
        print("  eligibility: UNSCREENED — nobody has checked their published criteria")
    if inv.get("eligibility_criterion"):
        print(f"    criterion: {inv['eligibility_criterion']}")
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
            # Flagged inline rather than in a separate section, because the question this answers
            # is "is this row actionable", and it has to be answerable without leaving the row.
            # Suppressed for records already out of play — nobody is about to approach those, and
            # a marker on every line is a marker nobody reads.
            unscreened = (
                not (investor.get("eligibility") or "")
                and (investor.get("status") or "cold") not in CLOSED_STATUSES
            )
            flag = "  [UNSCREENED]" if unscreened else ""
            print(f"  [{investor['id']}] {label}{flag} — {touch_str}")
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


def _add_body_field(parser: argparse.ArgumentParser, dest: str, *, required: bool, help: str) -> None:
    """Add one free-text field in both forms: inline on argv, or read from a file.

    They are mutually exclusive because supplying both would leave it ambiguous which one was
    meant, and the whole point of the file form is that you can be sure what got stored.
    """
    flag = "--" + dest.replace("_", "-")
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument(flag, help=help)
    group.add_argument(
        f"{flag}-file",
        metavar="PATH",
        help=f"read {flag} from a file, or from stdin as '-'; use this for anything containing "
        "a currency figure or a $, which the shell will otherwise eat before pia sees it",
    )


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
    # The old example here was `$25k-100k` written with a bare $, which in a double-quoted shell
    # argument silently expands to `-100k`. The help text was demonstrating the fault it should warn
    # about. See PILOT-LOG.md L23.
    p.add_argument(
        "--check-size",
        help="e.g. '$25k-100k' — single-quote anything with a $, or the shell will eat the figure",
    )
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
    _add_body_field(p, "note", required=False, help="free-text note on the record itself")
    p.set_defaults(func=cmd_investor)

    p = sub.add_parser(
        "intake",
        help="Log a counterparty somebody saw, before anything about it has been verified",
        description="Records identity and what the source claimed, as a sighting. Deliberately has "
        "no --check-size/--deadline/--stage-focus/--submission: those fields are for figures read "
        "off the counterparty's own site, and a claim from a post must not be able to look like one.",
    )
    p.add_argument("--id", required=True, help="stable slug, e.g. acme-ventures")
    p.add_argument("--firm", required=True, help="as the source names them; correct it later if they rebrand")
    p.add_argument(
        "--kind",
        choices=sorted(VALID_ENTITY_KINDS),
        help="only if the source actually says; omit when it is not yet clear what they are",
    )
    p.add_argument(
        "--source",
        default="LinkedIn screenshot",
        help="where this was seen (default: 'LinkedIn screenshot')",
    )
    p.add_argument("--source-url", help="the post/page it was seen on — not yet a verification")
    _add_body_field(
        p,
        "seen",
        required=True,
        help="what the source claimed: ask, cheque size, deadline, how to apply, who posted it",
    )
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser(
        "sheet",
        help="Refresh the Apple Numbers mirror of the ledger (read-only; the ledger always wins)",
    )
    p.add_argument(
        "--init",
        action="store_true",
        help="create the sheet first — run this once, then every pia write keeps it current",
    )
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser(
        "screen",
        help="Record an eligibility verdict against the counterparty's own published criteria",
        description="Both the criterion and the reason are required. A verdict with no evidence "
        "behind it is the same problem this field was added to fix, moved into a new field.",
    )
    p.add_argument("--investor", required=True, help="investor id")
    p.add_argument(
        "--verdict",
        required=True,
        choices=sorted(VALID_ELIGIBILITY),
        help="'ineligible' also sets status to screened-out — we ruled them out, they never said no",
    )
    p.add_argument(
        "--criterion",
        required=True,
        help="the published rule that decided it, e.g. 'excludes B2C; seed only; requires relocation'",
    )
    _add_body_field(
        p,
        "reason",
        required=True,
        help="what you actually read on their own site, and where",
    )
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("touch", help="Log an outreach touch (email, LinkedIn, intro, call)")
    p.add_argument("--investor", required=True, help="investor id")
    p.add_argument("--channel", required=True, choices=["email", "linkedin", "warm-intro", "event", "call", "other"])
    p.add_argument("--direction", required=True, choices=["outbound", "inbound"])
    p.add_argument(
        "--force-unscreened",
        action="store_true",
        help="log an outbound touch to a record nobody screened. The override is recorded on the "
        "touch, so a forced one stays distinguishable from a screened one afterwards.",
    )
    _add_body_field(p, "summary", required=True, help="what was actually said or sent")
    _add_body_field(p, "note", required=False, help="anything else worth keeping about this touch")
    p.set_defaults(func=cmd_touch)

    p = sub.add_parser("note", help="Log a research or meeting note")
    p.add_argument("--investor", required=True, help="investor id")
    p.add_argument("--kind", required=True, choices=["research", "meeting"])
    _add_body_field(p, "summary", required=True, help="what the research or meeting established")
    _add_body_field(p, "next_steps", required=False, help="what happens next, and who is blocked on what")
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
