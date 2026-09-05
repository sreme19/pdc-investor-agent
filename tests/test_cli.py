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
        "--summary", "sent intro", "--note-file", str(touch_note),
    )
    assert _records(run, "touch")[0]["note"] == "they asked about the $899K category figure"


def test_touch_summary_from_file(run, tmp_path):
    run("investor", "--id", "acme-vc", "--firm", "Acme Ventures")
    body = tmp_path / "s.md"
    body.write_text("pitched at a $3M valuation")
    run(
        "touch", "--investor", "acme-vc", "--channel", "email", "--direction", "outbound",
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
