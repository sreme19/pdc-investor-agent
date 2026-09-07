"""CLI-level tests, focused on the free-text input path.

The fault these exist for (PILOT-LOG.md L23): text passed on argv goes through the shell, which
expands `$55` to nothing before the process starts. A figure vanishes in transit and nothing in the
string is left to detect it by. The fix is a file/stdin path that never touches the shell, plus an
integrity echo that makes whatever did land checkable against the source.
"""

import io
import json

import pytest

from pdc_investor_agent import cli
from pdc_investor_agent.ledger import LEDGER_PATH_ENV


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    """Invoke the CLI against a throwaway ledger, returning (exit code, stdout)."""
    ledger_path = tmp_path / "records.jsonl"
    monkeypatch.setenv(LEDGER_PATH_ENV, str(ledger_path))
    monkeypatch.setattr(cli, "_stdin_consumed", False)

    def _run(*argv, stdin=None):
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = cli.main(list(argv))
        return code, capsys.readouterr().out

    _run.path = ledger_path
    return _run


def _records(run, kind):
    lines = run.path.read_text().splitlines()
    return [json.loads(line) for line in lines if json.loads(line)["kind"] == kind]


@pytest.fixture
def acme(run):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    return run


# -- the actual fix: a body that never passes through the shell --------------------


def test_note_summary_read_from_file_keeps_the_figure(acme, tmp_path):
    body = tmp_path / "note.md"
    body.write_text("IAN Fund 1 is a $55 million SEBI-registered fund.")
    code, out = acme("note", "--investor", "acme-vc", "--kind", "research", "--summary-file", str(body))

    assert code == 0
    stored = _records(acme, "note")[0]["summary"]
    assert "$55 million" in stored
    assert "55" in out


def test_note_summary_read_from_stdin(acme):
    code, _ = acme(
        "note", "--investor", "acme-vc", "--kind", "research", "--summary-file", "-",
        stdin="a $55 million fund\n",
    )
    assert code == 0
    assert _records(acme, "note")[0]["summary"] == "a $55 million fund"


def test_next_steps_file(acme, tmp_path):
    steps = tmp_path / "next.md"
    steps.write_text("ask for the $2.5M round terms")
    acme(
        "note", "--investor", "acme-vc", "--kind", "research",
        "--summary", "portfolio overlap", "--next-steps-file", str(steps),
    )
    assert _records(acme, "note")[0]["next_steps"] == "ask for the $2.5M round terms"


def test_touch_and_investor_bodies_also_take_files(run, tmp_path):
    inv_note = tmp_path / "inv.md"
    inv_note.write_text("cheque range is $500k-$5M")
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--note-file", str(inv_note))
    assert _records(run, "investor")[0]["note"] == "cheque range is $500k-$5M"

    touch_note = tmp_path / "touch.md"
    touch_note.write_text("they asked about the $899K category figure")
    run(
        "touch", "--investor", "acme-vc", "--channel", "email", "--direction", "outbound",
        # These tests are about the free-text path, not eligibility; the gate is covered below.
        "--force-unscreened",
        "--summary", "sent intro", "--note-file", str(touch_note),
    )
    assert _records(run, "touch")[0]["note"] == "they asked about the $899K category figure"


def test_touch_summary_from_file(run, tmp_path):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures")
    body = tmp_path / "s.md"
    body.write_text("pitched at a $3M valuation")
    run(
        "touch", "--investor", "acme-vc", "--channel", "email", "--direction", "outbound",
        # These tests are about the free-text path, not eligibility; the gate is covered below.
        "--force-unscreened",
        "--summary-file", str(body),
    )
    assert _records(run, "touch")[0]["summary"] == "pitched at a $3M valuation"


# -- the either/or contract ---------------------------------------------------------


def test_inline_and_file_forms_are_mutually_exclusive(acme, tmp_path):
    body = tmp_path / "note.md"
    body.write_text("something")
    with pytest.raises(SystemExit) as e:
        acme(
            "note", "--investor", "acme-vc", "--kind", "research",
            "--summary", "inline", "--summary-file", str(body),
        )
    assert e.value.code == 2


def test_summary_is_still_required_in_one_form_or_the_other(acme):
    with pytest.raises(SystemExit) as e:
        acme("note", "--investor", "acme-vc", "--kind", "research")
    assert e.value.code == 2


def test_inline_summary_still_works(acme):
    code, _ = acme("note", "--investor", "acme-vc", "--kind", "research", "--summary", "short one")
    assert code == 0
    assert _records(acme, "note")[0]["summary"] == "short one"


# -- refusing the bodies that are bugs ----------------------------------------------


def test_missing_file_is_an_error_not_an_empty_note(acme, tmp_path, capsys):
    code = cli.main([
        "note", "--investor", "acme-vc", "--kind", "research",
        "--summary-file", str(tmp_path / "nope.md"),
    ])
    assert code == 1
    assert "no such file" in capsys.readouterr().err
    assert _records(acme, "note") == []


def test_empty_file_is_refused(acme, tmp_path, capsys):
    body = tmp_path / "empty.md"
    body.write_text("   \n\n")
    code = cli.main([
        "note", "--investor", "acme-vc", "--kind", "research", "--summary-file", str(body),
    ])
    assert code == 1
    assert "empty" in capsys.readouterr().err
    assert _records(acme, "note") == []


def test_stdin_can_only_be_claimed_once(acme, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("a body"))
    code = cli.main([
        "note", "--investor", "acme-vc", "--kind", "research",
        "--summary-file", "-", "--next-steps-file", "-",
    ])
    assert code == 1
    assert "stdin was already read" in capsys.readouterr().err


# -- the integrity echo -------------------------------------------------------------


def test_echo_lists_every_figure_stored(acme, tmp_path):
    body = tmp_path / "note.md"
    body.write_text("Rs 50 Lakh to Rs 3 Crore, a 2.5% fee, across 1,160 deals.")
    _, out = acme("note", "--investor", "acme-vc", "--kind", "research", "--summary-file", str(body))

    line = next(ln for ln in out.splitlines() if "figures:" in ln)
    assert "4 figures: 50, 3, 2.5, 1,160" in line


def test_echo_reports_a_body_with_no_figures(acme):
    _, out = acme("note", "--investor", "acme-vc", "--kind", "research", "--summary", "no numbers here")
    assert "no figures" in out


def test_echo_char_count_matches_what_was_stored(acme, tmp_path):
    body = tmp_path / "note.md"
    body.write_text("a $55 million fund")
    _, out = acme("note", "--investor", "acme-vc", "--kind", "research", "--summary-file", str(body))
    assert f"stored {len('a $55 million fund')} chars" in out


def test_investor_echo_surfaces_check_size(run):
    _, out = run(
        "investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--check-size", "$25k-100k",
    )
    assert "check size: $25k-100k" in out
    assert "25, 100" in out


def test_echo_says_figure_not_figures_for_one(acme):
    _, out = acme("note", "--investor", "acme-vc", "--kind", "research", "--summary", "just 1 number")
    assert "1 figure: 1" in out


def test_figures_helper_keeps_decimals_and_separators_whole():
    assert cli._figures("2.5% of 1,160 across 80 deals.") == ["2.5", "1,160", "80"]


# -- intake ----------------------------------------------------------------------
#
# The screenshot path (PILOT-LOG.md L2). What matters here is the separation the command exists to
# enforce: a claim from a post lands as a `sighting` note and never as a verified field.


def test_intake_writes_an_investor_stub_and_a_sighting(run):
    code, out = run(
        "intake", "--id", "acme-vc", "--firm", "Acme Ventures",
        "--seen", "post claims pre-seed cheques, applications close October",
    )
    assert code == 0
    investors = _records(run, "investor")
    notes = _records(run, "note")
    assert len(investors) == 1
    assert investors[0]["firm"] == "Acme Ventures"
    assert investors[0]["status"] == "cold"
    assert investors[0]["source"] == "LinkedIn screenshot"
    assert len(notes) == 1
    assert notes[0]["note_kind"] == "sighting"
    assert "close October" in notes[0]["summary"]
    assert "nothing verified yet" in out


def test_intake_cannot_write_claims_into_verified_fields(run):
    """The omission is the feature: a cheque size seen in a post must not be able to look like one
    read off the counterparty's own site. See PILOT-LOG L6/L19."""
    for flag in ("--check-size", "--deadline", "--stage-focus", "--submission"):
        with pytest.raises(SystemExit):
            run("intake", "--id", "x", "--firm", "X", "--seen", "s", flag, "whatever")

    # Nothing was written at all — argparse rejected each call before the ledger was touched.
    assert not run.path.exists()


def test_intake_leaves_verified_fields_empty(run):
    run("intake", "--id", "acme-vc", "--firm", "Acme Ventures", "--seen", "claims $500k cheques")
    investor = _records(run, "investor")[0]
    assert investor["check_size"] == ""
    assert investor["deadline"] == ""
    assert investor["stage_focus"] == ""
    assert investor["submission"] == ""


def test_re_intake_does_not_drag_a_contacted_record_back_to_cold(run):
    run("intake", "--id", "acme-vc", "--firm", "Acme Ventures", "--seen", "first sighting")
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "contacted")
    _, out = run("intake", "--id", "acme-vc", "--firm", "Acme Ventures", "--seen", "seen again")

    from pdc_investor_agent.ledger import Ledger
    assert Ledger(path=run.path).latest_investor("acme-vc")["status"] == "contacted"
    assert "already in the ledger at status contacted" in out
    assert len(_records(run, "note")) == 2


def test_intake_body_can_come_from_a_file(run, tmp_path):
    body = tmp_path / "seen.md"
    body.write_text("post claims a $500k cheque and a 15 Oct close")
    _, out = run(
        "intake", "--id", "acme-vc", "--firm", "Acme Ventures", "--seen-file", str(body),
    )
    assert "500" in out and "15" in out
    assert "$500k" in _records(run, "note")[0]["summary"]


def test_intake_records_where_it_was_seen(run):
    run(
        "intake", "--id", "acme-vc", "--firm", "Acme Ventures", "--seen", "claims seed focus",
        "--source", "Twitter thread", "--source-url", "https://example.com/post/1",
    )
    investor = _records(run, "investor")[0]
    assert investor["source"] == "Twitter thread"
    assert investor["source_url"] == "https://example.com/post/1"


# -- the eligibility gate at the CLI ------------------------------------------------


def test_screen_records_the_verdict_and_its_evidence(run):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    code, out = run(
        "screen", "--investor", "acme-vc", "--verdict", "eligible",
        "--criterion", "seed consumer, no sector exclusion",
        "--reason", "their site lists seed and names no excluded sectors",
    )
    assert code == 0
    assert "eligible" in out
    assert _records(run, "investor")[-1]["eligibility"] == "eligible"
    assert _records(run, "note")[-1]["note_kind"] == "screening"


def test_screen_ineligible_reports_the_status_change(run):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    _, out = run(
        "screen", "--investor", "acme-vc", "--verdict", "ineligible",
        "--criterion", "excludes B2C", "--reason", "their FAQ puts consumer out of scope",
    )
    assert "screened-out" in out


def test_cli_refuses_an_outbound_touch_on_an_unscreened_record(run, capsys):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    code = cli.main([
        "touch", "--investor", "acme-vc", "--channel", "email",
        "--direction", "outbound", "--summary", "sent the deck",
    ])
    assert code == 1
    err = capsys.readouterr().err
    assert "nobody has screened" in err
    assert "pia screen" in err
    assert _records(run, "touch") == []


def test_cli_override_warns_on_stderr(run, capsys):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    code = cli.main([
        "touch", "--investor", "acme-vc", "--channel", "email", "--direction", "outbound",
        "--summary", "sent the deck", "--force-unscreened",
    ])
    assert code == 0
    assert "logged past the eligibility gate" in capsys.readouterr().err


def test_show_always_states_the_eligibility_even_when_unset(run):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    _, out = run("show", "acme-vc")
    assert "UNSCREENED" in out


def test_pipeline_flags_unscreened_but_not_closed_records(run):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    run("investor", "--id", "dead-vc", "--firm", "Dead Ventures", "--status", "screened-out")
    _, out = run("pipeline")

    cold_line = next(ln for ln in out.splitlines() if "acme-vc" in ln)
    closed_line = next(ln for ln in out.splitlines() if "dead-vc" in ln)
    assert "[UNSCREENED]" in cold_line
    # Nobody is about to approach a closed record, and a marker on every line is one nobody reads.
    assert "[UNSCREENED]" not in closed_line


def test_pipeline_drops_the_flag_once_screened(run):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures", "--status", "cold")
    run(
        "screen", "--investor", "acme-vc", "--verdict", "eligible",
        "--criterion", "seed consumer", "--reason", "read on their site",
    )
    _, out = run("pipeline")
    assert "[UNSCREENED]" not in out


def test_pipeline_suppresses_the_unrecorded_marker_only_for_rolling():
    """16 of 22 live records were rolling with no provenance; marking every row marks nothing."""
    from pdc_investor_agent.cli import _deadline_line

    rolling_old = {"deadline": "rolling"}
    dated_old = {"deadline": "2026-11-01"}

    # pipeline: rolling goes quiet, a real date does not
    assert _deadline_line(rolling_old, terse=True) == "deadline: rolling"
    assert "provenance unrecorded" in _deadline_line(dated_old, terse=True)

    # show: everything keeps its marker
    assert "provenance unrecorded" in _deadline_line(rolling_old)
    assert "provenance unrecorded" in _deadline_line(dated_old)

    # a rolling claim from a post is still a claim, and stays marked even in pipeline
    from_post = {"deadline": "rolling", "deadline_source": "social"}
    assert "UNVERIFIED" in _deadline_line(from_post, terse=True)

    # verified provenance prints plainly in both views
    verified = {"deadline": "rolling", "deadline_source": "first-party-page"}
    assert _deadline_line(verified, terse=True) == "deadline: rolling  (per first-party-page)"
