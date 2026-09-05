"""One-way mirror of the JSONL ledger into the Apple Numbers sheet the user actually reads.

`ledger/records.jsonl` is the source of truth. This module only ever writes *into* the Numbers
file, never back out of it, so the ledger always wins and the sheet is read-only in practice —
same contract as `job-hunt-agent`'s `numbers_mirror.py`, which mirrors an xlsx into the Career
Hacking Tracker. Editing a cell by hand here is not an error the code can catch; the next write
simply overwrites it.

Two differences from that implementation, both because of what this ledger already is:

  - There is no intermediate spreadsheet. That mirror syncs xlsx -> numbers sheet-for-sheet;
    this one renders the folded JSONL straight into rows, so there is one file to keep in step
    rather than two.
  - Rows are matched on a single real primary key. `job-hunt-agent` has to synthesise a row
    identity out of `Date + Company + Role / Title` and count repeats, because a job ledger has
    no stable id. Every record here has `id`, so a row can be found again by one column, and two
    genuinely different records can never collapse into one.

Matching by key rather than by position is what lets the user sort the sheet however they like:
the ledger stays in append order, the sheet stays in whatever order it is on screen, and a sync
finds each row by its key instead of rewriting the sort. New records land in the first blank row,
i.e. at the bottom of the user's current order.

Failures here never block a ledger write. The JSONL is the record; the sheet is a convenience.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from pdc_investor_agent.ledger import UNSCREENED

PIPELINE_SHEET = "Pipeline"
HISTORY_SHEET = "Touches & Notes"
RESEARCH_SHEET = "Research Files"
LEGEND_SHEET = "Legend"

# Sheet -> the column holding each row's identity. A sheet listed here is synced by key: columns
# matched by header name, rows matched by this column's value. Sheets not listed are rendered
# wholesale from scratch every time, which is only safe because nothing but this module writes them.
KEYED_SHEETS = {PIPELINE_SHEET: "ID", HISTORY_SHEET: "Entry ID"}

PIPELINE_HEADERS = [
    "First Seen",
    "ID",
    "Firm",
    "Kind",
    "Status",
    "Eligibility",
    "Screened On",
    "Criterion",
    "Stage Focus",
    "Check Size",
    "Deadline",
    "Submission",
    "Contact",
    "Source",
    "Source URL",
    "Last Touch",
    "Days Since Touch",
    "Next Action",
    "Notes",
]

HISTORY_HEADERS = [
    "Date",
    "ID",
    "Firm",
    "Entry",
    "Channel / Kind",
    "Direction",
    "Summary",
    "Next Steps",
    # Last on purpose: it is machinery, not something to read. It exists so a sorted sheet can be
    # re-found row by row, the same job `Date + Company + Role` does in the job-hunt mirror.
    "Entry ID",
]

RESEARCH_HEADERS = ["File", "Relates To", "Last Modified", "Words"]

# Written once per sync, wholesale. The status vocabulary is the part of this ledger that cannot be
# guessed from the sheet, and getting it wrong loses the story — see SPEC.md "Ledger shape".
LEGEND_ROWS = [
    ["PDC INVESTOR PIPELINE", ""],
    ["", ""],
    ["This sheet is a read-only mirror.", "Edits here are overwritten on the next `pia` write."],
    ["Source of truth", "ledger/records.jsonl (gitignored — never commit it)"],
    ["Rebuild by hand", "pia sheet"],
    ["", ""],
    ["STATUS", ""],
    ["cold", "In the pipeline, nobody contacted yet."],
    ["contacted", "We have reached out. No reply yet, or a reply that went nowhere."],
    ["meeting", "A real conversation happened or is booked."],
    ["diligence", "They are actively looking at the company."],
    ["committed", "They are in. Paperwork and money happen outside this repo."],
    ["passed", "THEY said no, after contact."],
    ["screened-out", "WE ruled them out before contacting anyone."],
    ["declined", "We turned them down."],
    ["", "passed and screened-out are deliberately different. Six months on, that is the story."],
    ["", ""],
    ["ELIGIBILITY", "Separate from status: has anyone checked their published criteria?"],
    ["unscreened", "Nobody has looked. NOT a verdict — an outbound touch is blocked."],
    ["eligible", "Checked against their own published rules, and we qualify."],
    ["ineligible", "Checked, and we do not qualify. Status goes to screened-out with it."],
    ["", "Criterion names the published rule that decided it. A verdict without one is not one."],
    ["", ""],
    ["KIND", ""],
    ["fund", "Institutional VC."],
    ["angel", "Individual angel, angel network, or syndicate."],
    ["accelerator", "Cohort programme. Has eligibility criteria and a close date."],
    ["programme", "Government or sovereign programme."],
    ["grant", "Non-dilutive pool."],
    ["intermediary", "Broker/platform. Establish the fee structure before a deck moves."],
    ["", ""],
    ["DEADLINE", ""],
    ["(blank)", "Nobody has checked. Not the same as there being no deadline."],
    ["rolling", "Somebody checked, and there is no date."],
    ["YYYY-MM", "Only a month was published. A day would be invention."],
    ["YYYY-MM-DD", "A published date."],
]


class SheetError(Exception):
    """Raised when the Numbers file cannot be written. Never fatal to a ledger write."""


def default_sheet_path(ledger_path: Path) -> Path:
    """The mirror sits beside the ledger, inside the gitignored `ledger/` folder (SPEC decision 2)."""
    return ledger_path.parent / "PDC Investor Pipeline 2026.numbers"


def _norm(value) -> str:
    return "" if value is None else str(value).strip()


def _unchanged(existing, value) -> bool:
    """Is the cell already holding this value?

    Numeric cells need comparing as numbers, not as text. Numbers stores every number as a double,
    so an int written as `868` reads back as `868.0` and a naive string comparison calls it a
    change every time. That looked harmless and was not: the mirror never converged, so every
    single `pia` command rewrote and re-saved the file and "already in sync" could never happen.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(existing, (int, float)) and not isinstance(existing, bool):
            return float(existing) == float(value)
        return False
    return _norm(existing) == _norm(value)


def _age_days(ts: str, now: datetime) -> int:
    then = datetime.fromisoformat(ts)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).days


# -- row building ----------------------------------------------------------------


def _first_seen(records: list[dict]) -> dict[str, str]:
    """Earliest investor line per id.

    `fold()` carries the *latest* timestamp forward, which is the right answer for "when did this
    last change" and the wrong one for "when did this enter the pipeline". The sheet wants the latter.
    """
    first: dict[str, str] = {}
    for record in records:
        if record["kind"] == "investor":
            first.setdefault(record["id"], record["ts"])
    return first


def _latest_next_steps(records: list[dict]) -> dict[str, str]:
    """The most recent non-empty `next_steps` per investor — the sheet's "Next Action" column."""
    latest: dict[str, str] = {}
    for record in records:
        if record["kind"] == "note" and _norm(record.get("next_steps")):
            latest[record["investor_id"]] = _norm(record["next_steps"])
    return latest


def _screened_on(records: list[dict]) -> dict[str, str]:
    """When the latest eligibility verdict was recorded, from the screening note that carries it.

    Derived rather than stored as its own field: `fold()` already collapses investor lines, so a
    separate timestamp column would need keeping in step by hand for no gain.
    """
    when: dict[str, str] = {}
    for record in records:
        if record["kind"] == "note" and record.get("note_kind") == "screening":
            when[record["investor_id"]] = record["ts"][:10]
    return when


def build_pipeline_rows(ledger, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    records = ledger.read_all()
    folded = ledger.fold()
    first_seen = _first_seen(records)
    next_actions = _latest_next_steps(records)
    screened_on = _screened_on(records)

    last_touch: dict[str, dict] = {}
    for touch in folded["touches"]:
        last_touch[touch["investor_id"]] = touch

    rows = []
    for investor_id, investor in folded["investors"].items():
        touch = last_touch.get(investor_id)
        rows.append(
            {
                "First Seen": first_seen.get(investor_id, investor["ts"])[:10],
                "ID": investor_id,
                "Firm": _norm(investor.get("firm")),
                "Kind": _norm(investor.get("entity_kind")),
                # A record that never carried a status reads as cold — same rule as `pia pipeline`.
                "Status": _norm(investor.get("status")) or "cold",
                # Never blank. A blank cell reads as "not applicable"; the whole point of this
                # column is that "nobody checked" is a state worth seeing, not an absence.
                "Eligibility": _norm(investor.get("eligibility")) or UNSCREENED,
                "Screened On": screened_on.get(investor_id, ""),
                "Criterion": _norm(investor.get("eligibility_criterion")),
                "Stage Focus": _norm(investor.get("stage_focus")),
                "Check Size": _norm(investor.get("check_size")),
                "Deadline": _norm(investor.get("deadline")),
                "Submission": _norm(investor.get("submission")),
                "Contact": _norm(investor.get("contact")),
                "Source": _norm(investor.get("source")),
                "Source URL": _norm(investor.get("source_url")),
                "Last Touch": f"{touch['ts'][:10]} ({touch['channel']})" if touch else "",
                # A number, not a string, so the column sorts numerically in Numbers. Blank rather
                # than 0 when there is no touch: zero would read as "touched today".
                "Days Since Touch": _age_days(touch["ts"], now) if touch else "",
                "Next Action": next_actions.get(investor_id, ""),
                "Notes": _norm(investor.get("note")),
            }
        )
    rows.sort(key=lambda r: (r["Status"], r["ID"]))
    return rows


def build_history_rows(ledger) -> list[dict]:
    """Every touch and note, in the order they were written.

    File order rather than sorted-by-timestamp: timestamps are second-granular, so a note and a
    touch logged in the same second tie, and write order is the only record of what really came
    first. Same reasoning as `Ledger.show()`.
    """
    folded = ledger.fold()
    firms = {i: _norm(r.get("firm")) for i, r in folded["investors"].items()}

    rows = []
    seen: dict[tuple[str, str], int] = {}
    for record in ledger.read_all():
        if record["kind"] not in ("touch", "note"):
            continue
        investor_id = record["investor_id"]
        base = (investor_id, record["ts"])
        seen[base] = seen.get(base, 0) + 1
        is_touch = record["kind"] == "touch"
        rows.append(
            {
                "Date": record["ts"][:10],
                "ID": investor_id,
                "Firm": firms.get(investor_id, ""),
                "Entry": "touch" if is_touch else "note",
                "Channel / Kind": record["channel"] if is_touch else record["note_kind"],
                "Direction": record["direction"] if is_touch else "",
                "Summary": _norm(record.get("summary")),
                "Next Steps": _norm(record.get("next_steps")) or _norm(record.get("note")),
                # Two entries can share an investor and a second, so the occurrence count is part
                # of the key. Without it they would compete for one row and one would vanish.
                "Entry ID": f"{investor_id}#{record['ts']}#{seen[base]}",
            }
        )
    return rows


def build_research_rows(ledger) -> list[dict]:
    """The loose markdown beside the ledger, and which record (if any) each one belongs to.

    This exists for PILOT-LOG L17: the most decision-relevant research in the pilot was about the
    *sector*, not any one counterparty, so it had nowhere to hang — every `note` needs an investor
    id. Those files ended up invisible to the CLI and to anyone who did not already know they were
    there. Listing them with an explicit "relates to no single record" is not a fix for L17, but it
    does stop them being invisible.
    """
    folded = ledger.fold()
    firms = {i: _norm(r.get("firm")) for i, r in folded["investors"].items()}
    directory = ledger.path.parent
    if not directory.exists():
        return []

    rows = []
    for path in sorted(directory.glob("*.md")):
        stem = path.stem
        related = ""
        for investor_id, firm in firms.items():
            # RESEARCH-acme-vc.md / DRAFT-acme-vc.md both name their record; a category file
            # like RESEARCH-category-notes.md matches nothing, which is the case worth seeing.
            if stem.lower().endswith(investor_id.lower()):
                related = f"{firm} [{investor_id}]"
                break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            words = len(text.split())
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        rows.append(
            {
                "File": path.name,
                "Relates To": related or "— no single record (applies to all)",
                "Last Modified": modified.date().isoformat(),
                "Words": words,
            }
        )
    return rows


# -- sheet writing ---------------------------------------------------------------


def _find_table(doc, sheet_name: str):
    for sheet in doc.sheets:
        if sheet.name == sheet_name:
            return sheet.tables[0]
    return None


def _ensure_table(doc, sheet_name: str):
    table = _find_table(doc, sheet_name)
    if table is not None:
        return table
    doc.add_sheet(sheet_name, sheet_name)
    return _find_table(doc, sheet_name)


def _grow(table, rows: int, cols: int) -> None:
    while table.num_rows < rows:
        table.add_row()
    while table.num_cols < cols:
        table.add_column()


def _align_headers(table, headers: list[str]) -> tuple[int, dict[str, int]]:
    """Map each header name to its column index in the sheet, adding any the sheet lacks.

    Matching by name is what lets the user reorder columns on screen without the mirror writing
    values into the wrong ones.
    """
    existing = [_norm(table.cell(0, c).value) for c in range(table.num_cols)]
    written = 0
    positions: dict[str, int] = {}
    for header in headers:
        if header in existing:
            positions[header] = existing.index(header)
            continue
        target = next((i for i, h in enumerate(existing) if not h), None)
        if target is None:
            table.add_column()
            existing.append("")
            target = table.num_cols - 1
        table.write(0, target, header)
        existing[target] = header
        positions[header] = target
        written += 1
    return written, positions


def _row_keys_in_sheet(table, key_column: int) -> dict[str, int]:
    keys: dict[str, int] = {}
    for r in range(1, table.num_rows):
        key = _norm(table.cell(r, key_column).value)
        if key and key not in keys:
            keys[key] = r
    return keys


def _delete_orphans(table, key_column: int, live_keys: set[str], sheet_name: str) -> int:
    """Drop sheet rows the ledger no longer has. The ledger defines what exists.

    In practice this should almost never fire: the JSONL is append-only, so a record does not
    disappear. If it fires in bulk, the sheet and the ledger are not the same data — a copied file,
    a wrong path — and overwriting would destroy whatever the sheet actually held. So bulk is an
    error, not a sync.
    """
    present = _row_keys_in_sheet(table, key_column)
    orphans = sorted(row for key, row in present.items() if key not in live_keys)
    if not orphans:
        return 0
    if live_keys and len(orphans) == len(present):
        raise SheetError(
            f"refusing to sync {sheet_name!r}: none of its {len(present)} rows match a record in "
            "the ledger, so the sheet and the ledger look like different data. Check the sheet's "
            "key column before re-running."
        )
    for row in reversed(orphans):
        table.delete_row(1, start_row=row)
    return len(orphans)


def _claim_blank_row(table, positions: dict[str, int], claimed: set[int]) -> int:
    for r in range(1, table.num_rows):
        if r in claimed:
            continue
        if not any(_norm(table.cell(r, c).value) for c in positions.values()):
            return r
    table.add_row()
    return table.num_rows - 1


def _sync_keyed(table, headers: list[str], rows: list[dict], key_header: str, sheet_name: str) -> int:
    _grow(table, len(rows) + 1, len(headers))
    changed, positions = _align_headers(table, headers)
    key_column = positions[key_header]

    changed += _delete_orphans(table, key_column, {str(r[key_header]) for r in rows}, sheet_name)

    # Rebuilt after the deletions above, because deleting a row shifts every row below it.
    present = _row_keys_in_sheet(table, key_column)
    claimed: set[int] = set()
    for row in rows:
        target = present.get(str(row[key_header]))
        if target is None:
            target = _claim_blank_row(table, positions, claimed)
        claimed.add(target)
        for header in headers:
            value = row[header]
            if not _unchanged(table.cell(target, positions[header]).value, value):
                table.write(target, positions[header], value)
                changed += 1
    return changed


def _sync_wholesale(table, rows: list[list]) -> int:
    """Render a small fixed sheet top-left, then blank anything left over from a longer previous run."""
    width = max((len(row) for row in rows), default=0)
    _grow(table, max(len(rows), 1), max(width, 1))
    changed = 0
    for r, row in enumerate(rows):
        for c in range(width):
            value = row[c] if c < len(row) else ""
            if not _unchanged(table.cell(r, c).value, value):
                table.write(r, c, value)
                changed += 1
    for r in range(len(rows), table.num_rows):
        for c in range(min(width, table.num_cols)):
            if _norm(table.cell(r, c).value):
                table.write(r, c, "")
                changed += 1
    return changed


def _as_matrix(headers: list[str], rows: list[dict]) -> list[list]:
    return [headers] + [[row[h] for h in headers] for row in rows]


def _load_document(path: Path):
    try:
        from numbers_parser import Document
    except ImportError as e:  # pragma: no cover - declared in pyproject
        raise SheetError(
            "numbers-parser is not installed — run `uv pip install -e .` to enable the sheet."
        ) from e
    return Document


def create(path: Path) -> str:
    """Create the mirror file with its four sheets. Refuses to clobber an existing one."""
    Document = _load_document(path)
    if path.exists():
        raise SheetError(f"{path.name} already exists — run `pia sheet` to refresh it instead.")
    doc = Document()
    # A new document comes with one sheet called "Sheet 1" and there is no way to remove a sheet,
    # so the first sheet is renamed into service rather than left orphaned beside the real ones.
    doc.sheets[0].name = PIPELINE_SHEET
    doc.sheets[0].tables[0].name = PIPELINE_SHEET
    for name in (HISTORY_SHEET, RESEARCH_SHEET, LEGEND_SHEET):
        doc.add_sheet(name, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return f"created {path}"


def mirror(ledger, path: Path) -> str:
    """Render the ledger into the Numbers file. Returns a one-line summary."""
    Document = _load_document(path)
    if not path.exists():
        raise SheetError(
            f"no sheet at {path} — run `pia sheet --init` once to create it."
        )

    # Taken before anything is written, for the same reason the job-hunt ledger snapshots its xlsx:
    # this file holds data that exists nowhere in git.
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)

    try:
        doc = Document(str(path))
    except Exception as e:
        raise SheetError(f"could not open {path}: {e}") from e

    plan = [
        (PIPELINE_SHEET, PIPELINE_HEADERS, build_pipeline_rows(ledger)),
        (HISTORY_SHEET, HISTORY_HEADERS, build_history_rows(ledger)),
        (RESEARCH_SHEET, RESEARCH_HEADERS, build_research_rows(ledger)),
    ]

    total = 0
    touched: list[str] = []
    for sheet_name, headers, rows in plan:
        table = _ensure_table(doc, sheet_name)
        if table is None:
            raise SheetError(f"could not create sheet {sheet_name!r}")
        key_header = KEYED_SHEETS.get(sheet_name)
        if key_header:
            changed = _sync_keyed(table, headers, rows, key_header, sheet_name)
        else:
            changed = _sync_wholesale(table, _as_matrix(headers, rows))
        if changed:
            touched.append(f"{sheet_name} ({changed})")
        total += changed

    legend = _ensure_table(doc, LEGEND_SHEET)
    if legend is not None:
        changed = _sync_wholesale(legend, LEGEND_ROWS)
        if changed:
            touched.append(f"{LEGEND_SHEET} ({changed})")
        total += changed

    if total == 0:
        return "sheet already in sync"

    try:
        doc.save(str(path))
    except Exception as e:
        raise SheetError(
            f"could not save {path} — close it in Numbers first, then run `pia sheet`. "
            f"A pre-write snapshot is at {backup.name}: {e}"
        ) from e

    return f"sheet updated: {total} cells across {', '.join(touched)}"
