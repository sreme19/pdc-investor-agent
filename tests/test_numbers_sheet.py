"""Tests for the Apple Numbers mirror.

The two properties worth defending, because breaking either is silent:

  - The sheet is rendered from the ledger, so the numbers in it must be the numbers in the JSONL.
  - The user sorts the sheet. Rows are matched by key, not by position, so a sync must find the
    same row again after it has been moved and must not rewrite the sort.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pdc_investor_agent.ledger import Ledger
from pdc_investor_agent.numbers_sheet import (
    HISTORY_SHEET,
    PIPELINE_HEADERS,
    PIPELINE_SHEET,
    RESEARCH_SHEET,
    SheetError,
    build_history_rows,
    build_pipeline_rows,
    build_research_rows,
    create,
    default_sheet_path,
    mirror,
)

numbers_parser = pytest.importorskip("numbers_parser")


@pytest.fixture
def ledger(tmp_path):
    return Ledger(path=tmp_path / "records.jsonl")


@pytest.fixture
def sheet(ledger):
    path = default_sheet_path(ledger.path)
    create(path)
    return path


def _table(path, sheet_name):
    doc = numbers_parser.Document(str(path))
    for s in doc.sheets:
        if s.name == sheet_name:
            return s.tables[0]
    raise AssertionError(f"no sheet {sheet_name!r}")


def _rows_by_key(path, sheet_name, key_header):
    """The sheet as {key: {header: value}}, read back the way a human reading it would."""
    table = _table(path, sheet_name)
    headers = [table.cell(0, c).value for c in range(table.num_cols)]
    key_col = headers.index(key_header)
    out = {}
    for r in range(1, table.num_rows):
        key = table.cell(r, key_col).value
        if not key:
            continue
        out[str(key)] = {
            str(h): table.cell(r, c).value for c, h in enumerate(headers) if h
        }
    return out


# -- row building ----------------------------------------------------------------


def test_pipeline_row_uses_first_seen_not_last_updated(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")
    row = build_pipeline_rows(ledger)[0]
    first, last = (r["ts"] for r in ledger.read_all() if r["kind"] == "investor")
    assert row["First Seen"] == first[:10]
    assert row["Status"] == "contacted"
    assert last  # both lines are still in the file


def test_statusless_record_reads_as_cold(ledger):
    ledger.investor("acme-vc", "Acme Ventures")
    assert build_pipeline_rows(ledger)[0]["Status"] == "cold"


def test_days_since_touch_is_blank_not_zero_when_never_touched(ledger):
    """0 would read as "touched today", which is the opposite of the truth."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    row = build_pipeline_rows(ledger)[0]
    assert row["Days Since Touch"] == ""
    assert row["Last Touch"] == ""


def test_days_since_touch_counts_from_the_latest_touch(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "outbound", "intro", force_unscreened=True)
    now = datetime.now(timezone.utc) + timedelta(days=9)
    row = build_pipeline_rows(ledger, now=now)[0]
    assert row["Days Since Touch"] == 9
    assert row["Last Touch"].endswith("(email)")


def test_next_action_is_the_latest_non_empty_next_steps(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.note("acme-vc", "research", "first pass", next_steps="find a warm intro")
    ledger.note("acme-vc", "research", "second pass with no next step")
    ledger.note("acme-vc", "meeting", "call happened", next_steps="send the deck")
    assert build_pipeline_rows(ledger)[0]["Next Action"] == "send the deck"


def test_history_entries_in_the_same_second_get_distinct_keys(ledger):
    """Timestamps are second-granular, so two entries can tie. If they shared a key they would
    compete for one row in the sheet and one of them would silently disappear."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.note("acme-vc", "research", "note one")
    ledger.note("acme-vc", "research", "note two")
    ledger.touch("acme-vc", "email", "outbound", "touch one", force_unscreened=True)
    rows = build_history_rows(ledger)
    assert len(rows) == 3
    assert len({r["Entry ID"] for r in rows}) == 3
    assert [r["Summary"] for r in rows] == ["note one", "note two", "touch one"]


def test_research_files_are_linked_to_a_record_or_marked_unlinked(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    (ledger.path.parent / "RESEARCH-acme-vc.md").write_text("a b c")
    (ledger.path.parent / "RESEARCH-category-notes.md").write_text("x y")

    rows = {r["File"]: r["Relates To"] for r in build_research_rows(ledger)}
    assert "Acme Ventures [acme-vc]" == rows["RESEARCH-acme-vc.md"]
    # PILOT-LOG L17: category research belongs to every record, so it belongs to no id.
    assert "no single record" in rows["RESEARCH-category-notes.md"]


# -- syncing ---------------------------------------------------------------------


def test_create_then_mirror_writes_the_ledger_into_the_sheet(ledger, sheet):
    ledger.investor(
        "acme-vc",
        "Acme Ventures",
        entity_kind="fund",
        check_size="$25k-100k",
        deadline="rolling",
        deadline_source="first-party-page",
        status="cold",
    )
    mirror(ledger, sheet)

    row = _rows_by_key(sheet, PIPELINE_SHEET, "ID")["acme-vc"]
    assert row["Firm"] == "Acme Ventures"
    assert row["Kind"] == "fund"
    assert row["Check Size"] == "$25k-100k"
    assert row["Deadline"] == "rolling"
    assert row["Status"] == "cold"


def test_create_refuses_to_clobber_an_existing_sheet(ledger, sheet):
    with pytest.raises(SheetError, match="already exists"):
        create(sheet)


def test_mirror_without_a_sheet_says_how_to_make_one(ledger):
    with pytest.raises(SheetError, match="--init"):
        mirror(ledger, default_sheet_path(ledger.path))


def test_second_mirror_with_no_changes_is_a_no_op(ledger, sheet):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    mirror(ledger, sheet)
    assert mirror(ledger, sheet) == "sheet already in sync"


def test_status_change_updates_the_existing_row_rather_than_adding_one(ledger, sheet):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    mirror(ledger, sheet)
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")
    mirror(ledger, sheet)

    rows = _rows_by_key(sheet, PIPELINE_SHEET, "ID")
    assert len(rows) == 1
    assert rows["acme-vc"]["Status"] == "contacted"


def test_user_sort_order_survives_a_sync(ledger, sheet):
    """The whole reason rows are matched by key instead of by position.

    The user sorts the sheet; the ledger stays in append order. A positional sync would write
    Acme's values into Zenith's row and rewrite the sort on every single command.
    """
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.investor("zenith-vc", "Zenith Ventures", status="cold")
    mirror(ledger, sheet)

    # Reverse the two rows in the sheet, as sorting by Firm descending would.
    doc = numbers_parser.Document(str(sheet))
    table = next(s.tables[0] for s in doc.sheets if s.name == PIPELINE_SHEET)
    headers = [table.cell(0, c).value for c in range(table.num_cols)]
    original = {
        str(table.cell(r, headers.index("ID")).value): [
            table.cell(r, c).value for c in range(table.num_cols)
        ]
        for r in (1, 2)
    }
    for c in range(table.num_cols):
        table.write(1, c, original["zenith-vc"][c] or "")
        table.write(2, c, original["acme-vc"][c] or "")
    doc.save(str(sheet))

    ledger.investor("acme-vc", "Acme Ventures", status="contacted")
    mirror(ledger, sheet)

    table = _table(sheet, PIPELINE_SHEET)
    headers = [table.cell(0, c).value for c in range(table.num_cols)]
    id_col = headers.index("ID")
    status_col = headers.index("Status")
    assert table.cell(1, id_col).value == "zenith-vc"
    assert table.cell(2, id_col).value == "acme-vc"
    assert table.cell(2, status_col).value == "contacted"


def test_reordered_columns_are_still_written_correctly(ledger, sheet):
    """Columns are matched by header name, so moving one in Numbers must not misfile values."""
    ledger.investor("acme-vc", "Acme Ventures", entity_kind="fund", status="cold")
    mirror(ledger, sheet)

    doc = numbers_parser.Document(str(sheet))
    table = next(s.tables[0] for s in doc.sheets if s.name == PIPELINE_SHEET)
    # Swap two whole columns, header and data together — what dragging a column in Numbers does.
    # Moving the header alone would leave a date sitting under the "ID" heading, which is a
    # corrupted sheet rather than a reordered one, and is caught by the orphan guard instead.
    for r in range(table.num_rows):
        left, right = table.cell(r, 0).value, table.cell(r, 1).value
        table.write(r, 0, right or "")
        table.write(r, 1, left or "")
    doc.save(str(sheet))

    ledger.investor("acme-vc", "Acme Ventures", status="diligence")
    mirror(ledger, sheet)

    assert _rows_by_key(sheet, PIPELINE_SHEET, "ID")["acme-vc"]["Status"] == "diligence"


def test_sync_refuses_when_no_row_matches_the_ledger(ledger, sheet):
    """A sheet whose rows are all strangers is probably a different file, not a stale one.

    Overwriting it would destroy whatever it actually held, so this is an error rather than a sync.
    """
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    mirror(ledger, sheet)

    doc = numbers_parser.Document(str(sheet))
    table = next(s.tables[0] for s in doc.sheets if s.name == PIPELINE_SHEET)
    headers = [table.cell(0, c).value for c in range(table.num_cols)]
    table.write(1, headers.index("ID"), "some-other-ledgers-record")
    doc.save(str(sheet))

    with pytest.raises(SheetError, match="different data"):
        mirror(ledger, sheet)


def test_history_and_research_sheets_are_populated(ledger, sheet):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.note("acme-vc", "sighting", "post claims $500k cheques, closes October")
    ledger.touch("acme-vc", "email", "outbound", "sent the deck", force_unscreened=True)
    (ledger.path.parent / "RESEARCH-acme-vc.md").write_text("findings")
    mirror(ledger, sheet)

    history = _rows_by_key(sheet, HISTORY_SHEET, "Entry ID")
    assert len(history) == 2
    summaries = {r["Summary"] for r in history.values()}
    # The figure has to survive the whole path from ledger to sheet.
    assert "post claims $500k cheques, closes October" in summaries
    assert {r["Entry"] for r in history.values()} == {"note", "touch"}

    research = _table(sheet, RESEARCH_SHEET)
    assert research.cell(0, 0).value == "File"
    assert research.cell(1, 0).value == "RESEARCH-acme-vc.md"


def test_every_pipeline_header_is_written(ledger, sheet):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    mirror(ledger, sheet)
    table = _table(sheet, PIPELINE_SHEET)
    present = {table.cell(0, c).value for c in range(table.num_cols)}
    assert set(PIPELINE_HEADERS) <= present


def test_numeric_cells_do_not_count_as_changed_every_sync(ledger, sheet):
    """Regression: the mirror never converged.

    Numbers stores every number as a double, so `Words` written as int 868 read back as 868.0 and
    a string comparison called it a change forever. Every `pia` command rewrote and re-saved the
    file, and "already in sync" was unreachable. Caught only by running `pia sheet` three times and
    noticing the count never dropped — a mirror that reports work it did not need to do.
    """
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "outbound", "sent the deck", force_unscreened=True)
    (ledger.path.parent / "RESEARCH-acme-vc.md").write_text("a b c d e f g")
    mirror(ledger, sheet)

    assert mirror(ledger, sheet) == "sheet already in sync"
    assert mirror(ledger, sheet) == "sheet already in sync"


def test_a_real_change_is_still_detected_after_the_numeric_fix(ledger, sheet):
    """The other half of the regression: not-converging is one bug, never-updating is a worse one."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    (ledger.path.parent / "RESEARCH-acme-vc.md").write_text("one two")
    mirror(ledger, sheet)
    assert mirror(ledger, sheet) == "sheet already in sync"

    (ledger.path.parent / "RESEARCH-acme-vc.md").write_text("one two three four five")
    assert mirror(ledger, sheet) != "sheet already in sync"

    table = _table(sheet, RESEARCH_SHEET)
    headers = [table.cell(0, c).value for c in range(table.num_cols)]
    assert float(table.cell(1, headers.index("Words")).value) == 5


def test_sheet_shows_unscreened_rather_than_a_blank_cell(ledger, sheet):
    """A blank reads as "not applicable". The point of the column is that "nobody checked" shows."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    mirror(ledger, sheet)
    assert _rows_by_key(sheet, PIPELINE_SHEET, "ID")["acme-vc"]["Eligibility"] == "unscreened"


def test_sheet_carries_the_verdict_its_date_and_its_criterion(ledger, sheet):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.screen("acme-vc", "ineligible", "excludes B2C", "their FAQ puts consumer out of scope")
    mirror(ledger, sheet)

    row = _rows_by_key(sheet, PIPELINE_SHEET, "ID")["acme-vc"]
    assert row["Eligibility"] == "ineligible"
    assert row["Criterion"] == "excludes B2C"
    assert row["Screened On"] == datetime.now(timezone.utc).date().isoformat()
    assert row["Status"] == "screened-out"
