import json

import pytest

from pdc_investor_agent.ledger import Ledger, LedgerError


@pytest.fixture
def ledger(tmp_path):
    return Ledger(path=tmp_path / "records.jsonl")


def test_investor_roundtrip(ledger):
    ledger.investor("acme-vc", "Acme Ventures", stage_focus="seed", status="cold")
    records = ledger.read_all()
    assert len(records) == 1
    assert records[0]["kind"] == "investor"
    assert records[0]["firm"] == "Acme Ventures"


def test_invalid_status_rejected(ledger):
    with pytest.raises(LedgerError):
        ledger.investor("acme-vc", "Acme Ventures", status="not-a-status")


def test_touch_requires_existing_investor(ledger):
    with pytest.raises(LedgerError):
        ledger.touch("does-not-exist", "email", "outbound", "cold intro", force_unscreened=True)


def test_touch_and_note_lifecycle(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "outbound", "sent intro deck", force_unscreened=True)
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")
    ledger.note("acme-vc", "research", "portfolio overlap w/ two competitors", next_steps="ask for warm intro")

    folded = ledger.fold()
    assert len(folded["touches"]) == 1
    assert len(folded["notes"]) == 1
    assert folded["investors"]["acme-vc"]["status"] == "contacted"


def test_pipeline_groups_by_latest_status(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "outbound", "sent intro deck", force_unscreened=True)
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")

    pipeline = ledger.pipeline()
    assert "contacted" in pipeline["by_status"]
    assert pipeline["by_status"]["contacted"][0]["id"] == "acme-vc"
    assert "cold" not in pipeline["by_status"]
    assert pipeline["last_touch_by_investor"]["acme-vc"]["channel"] == "email"


def test_partial_update_does_not_blank_earlier_fields(ledger):
    """A later line is a partial update, not a replacement.

    Regression: `--status passed` on an existing record used to wipe contact/check-size/source,
    because folding took the newest line wholesale.
    """
    ledger.investor(
        "acme-vc",
        "Acme Ventures",
        contact="Dana Reyes <dana@acme.example>",
        check_size="$25k-100k",
        source="cold list",
        status="cold",
    )
    ledger.investor("acme-vc", "Acme Ventures", status="passed")

    merged = ledger.fold()["investors"]["acme-vc"]
    assert merged["status"] == "passed"
    assert merged["contact"] == "Dana Reyes <dana@acme.example>"
    assert merged["check_size"] == "$25k-100k"
    assert merged["source"] == "cold list"


def test_update_without_status_leaves_status_alone(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="meeting")
    ledger.investor("acme-vc", "Acme Ventures", contact="Dana Reyes")

    merged = ledger.fold()["investors"]["acme-vc"]
    assert merged["status"] == "meeting"
    assert merged["contact"] == "Dana Reyes"


def test_record_with_no_status_reads_as_cold(ledger):
    ledger.investor("acme-vc", "Acme Ventures")
    assert ledger.pipeline()["by_status"]["cold"][0]["id"] == "acme-vc"


def test_screened_out_is_distinct_from_passed(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="screened-out")
    ledger.investor("beta-labs", "Beta Labs", status="passed")

    by_status = ledger.pipeline()["by_status"]
    assert [r["id"] for r in by_status["screened-out"]] == ["acme-vc"]
    assert [r["id"] for r in by_status["passed"]] == ["beta-labs"]


def test_entity_kind_and_submission_validated(ledger):
    ledger.investor("acme-acc", "Acme Accelerator", entity_kind="accelerator", submission="form")
    merged = ledger.fold()["investors"]["acme-acc"]
    assert merged["entity_kind"] == "accelerator"
    assert merged["submission"] == "form"

    with pytest.raises(LedgerError):
        ledger.investor("acme-vc", "Acme Ventures", entity_kind="hedge-fund")
    with pytest.raises(LedgerError):
        ledger.investor("acme-vc", "Acme Ventures", submission="carrier-pigeon")


def test_deadline_accepts_a_date_or_rolling(ledger):
    ledger.investor("acme-acc", "Acme Accelerator", deadline="2027-02-01",
                    deadline_source="first-party-page")
    ledger.investor("beta-fund", "Beta Fund", deadline="rolling",
                    deadline_source="first-party-page")
    investors = ledger.fold()["investors"]
    assert investors["acme-acc"]["deadline"] == "2027-02-01"
    assert investors["beta-fund"]["deadline"] == "rolling"


def test_deadline_rejects_junk_and_impossible_dates(ledger):
    with pytest.raises(LedgerError):
        ledger.investor("acme-acc", "Acme Accelerator", deadline="next spring")
    with pytest.raises(LedgerError):
        ledger.investor("acme-acc", "Acme Accelerator", deadline="2027-02-31")


def test_show_returns_record_plus_history_oldest_first(ledger):
    ledger.investor("acme-vc", "Acme Ventures", entity_kind="fund", status="cold")
    ledger.note("acme-vc", "research", "seed-stage consumer fund")
    ledger.touch("acme-vc", "email", "outbound", "sent intro", force_unscreened=True)
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")

    detail = ledger.show("acme-vc")
    assert detail["investor"]["status"] == "contacted"
    assert detail["investor"]["entity_kind"] == "fund"
    assert [e["kind"] for e in detail["history"]] == ["note", "touch"]
    assert detail["history"] == sorted(detail["history"], key=lambda r: r["ts"])


def test_show_unknown_investor_is_none(ledger):
    assert ledger.show("does-not-exist") is None


def test_deadline_accepts_month_precision(ledger):
    """Programmes publish "closes February 2027" without a day; don't force one to be invented."""
    ledger.investor("acme-acc", "Acme Accelerator", deadline="2027-02",
                    deadline_source="first-party-page")
    assert ledger.fold()["investors"]["acme-acc"]["deadline"] == "2027-02"
    with pytest.raises(LedgerError):
        ledger.investor("acme-acc", "Acme Accelerator", deadline="2027-13")


# -- the eligibility gate (PILOT-LOG L31) -------------------------------------------
#
# The fault: `cold` could not distinguish "checked, they fit" from "nobody has looked", and
# `investor-outreach` drafts from the cold list. So the loop could write a careful, specific
# approach to a fund that excludes consumer dating by published policy.


def test_a_new_record_is_unscreened(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    assert ledger.fold()["investors"]["acme-vc"]["eligibility"] == ""


def test_outbound_touch_is_refused_on_an_unscreened_record(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    with pytest.raises(LedgerError, match="nobody has screened"):
        ledger.touch("acme-vc", "email", "outbound", "sent the deck")
    assert ledger.fold()["touches"] == []


def test_inbound_touch_is_never_blocked(ledger):
    """They wrote to us. Refusing to record that would lose real history to a rule about outreach."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "inbound", "they replied out of the blue")
    assert len(ledger.fold()["touches"]) == 1


def test_screening_eligible_unblocks_outbound(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.screen("acme-vc", "eligible", "seed consumer, no sector exclusion", "read on their site")
    ledger.touch("acme-vc", "email", "outbound", "sent the deck")
    assert len(ledger.fold()["touches"]) == 1


def test_screening_ineligible_also_screens_the_record_out(ledger):
    """One event, not two. Leaving the caller to keep them in step is how they drift."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.screen("acme-vc", "ineligible", "excludes B2C", "their FAQ says consumer is out of scope")

    merged = ledger.fold()["investors"]["acme-vc"]
    assert merged["eligibility"] == "ineligible"
    assert merged["status"] == "screened-out"
    assert merged["eligibility_criterion"] == "excludes B2C"


def test_outbound_to_an_ineligible_record_names_the_criterion(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.screen("acme-vc", "ineligible", "excludes B2C", "their FAQ says so")
    with pytest.raises(LedgerError, match="excludes B2C"):
        ledger.touch("acme-vc", "email", "outbound", "sent anyway")


def test_the_override_works_and_leaves_a_trace(ledger):
    """An override that leaves no trace is indistinguishable from the gate never being there."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    record = ledger.touch("acme-vc", "email", "outbound", "sent it", force_unscreened=True)
    assert record["forced_past_eligibility"] == "unscreened"


def test_a_screened_touch_carries_no_override_marker(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.screen("acme-vc", "eligible", "seed consumer", "read on their site")
    record = ledger.touch("acme-vc", "email", "outbound", "sent it", force_unscreened=True)
    assert "forced_past_eligibility" not in record


def test_a_verdict_needs_a_criterion_and_a_reason(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    with pytest.raises(LedgerError, match="criterion is required"):
        ledger.screen("acme-vc", "eligible", "   ", "some reason")
    with pytest.raises(LedgerError, match="reason is required"):
        ledger.screen("acme-vc", "eligible", "seed consumer", "  ")


def test_unscreened_cannot_be_recorded_as_a_verdict(ledger):
    """"Nobody looked" is the absence of a verdict. Being able to assert it would let a record
    look screened while saying nothing was found."""
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    with pytest.raises(LedgerError, match="not one you can record"):
        ledger.screen("acme-vc", "unscreened", "x", "y")


def test_screening_does_not_blank_the_rest_of_the_record(ledger):
    ledger.investor(
        "acme-vc", "Acme Ventures", contact="Dana Reyes", check_size="$25k-100k", status="cold",
    )
    ledger.screen("acme-vc", "eligible", "seed consumer", "read on their site")

    merged = ledger.fold()["investors"]["acme-vc"]
    assert merged["contact"] == "Dana Reyes"
    assert merged["check_size"] == "$25k-100k"
    assert merged["status"] == "cold"


def test_the_verdict_keeps_its_evidence_in_the_history(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.screen("acme-vc", "eligible", "seed consumer", "their site states seed, no exclusions")

    screening = [e for e in ledger.show("acme-vc")["history"] if e.get("note_kind") == "screening"]
    assert len(screening) == 1
    assert screening[0]["summary"] == "their site states seed, no exclusions"
    assert screening[0]["next_steps"] == "seed consumer"


def test_a_deadline_cannot_be_written_without_saying_where_it_came_from(ledger):
    """The L35 case: twice the deciding date came from press or social and looked verified."""
    with pytest.raises(LedgerError, match="deadline source"):
        ledger.investor("acme-acc", "Acme Accelerator", deadline="2026-10-02")
    # and the reverse: a provenance with nothing to be the provenance of
    with pytest.raises(LedgerError, match="nothing for it to source"):
        ledger.investor("acme-acc", "Acme Accelerator", deadline_source="press")


def test_deadline_source_rejects_anything_outside_the_four_states(ledger):
    with pytest.raises(LedgerError):
        ledger.investor(
            "acme-acc", "Acme Accelerator", deadline="2026-10-02", deadline_source="the organiser"
        )


def test_press_and_social_deadlines_read_as_untrusted_and_first_party_does_not(ledger):
    ledger.investor("acme-acc", "Acme Accelerator", deadline="2026-08-31", deadline_source="press")
    ledger.investor("beta-acc", "Beta Accelerator", deadline="2026-10-02",
                    deadline_source="first-party-page")
    investors = ledger.fold()["investors"]
    assert ledger.deadline_is_trusted(investors["acme-acc"]) is False
    assert ledger.deadline_is_trusted(investors["beta-acc"]) is True


def test_a_deadline_predating_the_field_is_neither_trusted_nor_untrusted(ledger):
    """A record written before provenance existed must not be rounded to either verdict."""
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    with ledger.path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "kind": "investor", "id": "old-acc", "ts": "2026-09-01T00:00:00+00:00",
            "firm": "Old Accelerator", "deadline": "2026-11-01",
        }) + "\n")
    old = ledger.fold()["investors"]["old-acc"]
    assert ledger.deadline_is_trusted(old) is None
    assert ledger.deadline_is_trusted({"deadline": ""}) is None


def test_submission_state_is_a_separate_fact_from_the_deadline(ledger):
    """They came apart once: window closed a week earlier, form still taking entries."""
    ledger.investor(
        "acme-acc", "Acme Accelerator",
        deadline="2026-08-31", deadline_source="press", submission_state="observed-accepting",
    )
    merged = ledger.fold()["investors"]["acme-acc"]
    assert merged["deadline"] == "2026-08-31"
    assert merged["submission_state"] == "observed-accepting"
    with pytest.raises(LedgerError):
        ledger.investor("acme-acc", "Acme Accelerator", submission_state="probably-open")


def test_conflicting_fields_must_name_fields_that_exist(ledger):
    ledger.investor("acme-acc", "Acme Accelerator", conflicting_fields="deadline, contact")
    assert ledger.fold()["investors"]["acme-acc"]["conflicting_fields"] == "deadline,contact"
    with pytest.raises(LedgerError, match="unknown field"):
        ledger.investor("acme-acc", "Acme Accelerator", conflicting_fields="venue")
    with pytest.raises(LedgerError, match="at least one field"):
        ledger.investor("acme-acc", "Acme Accelerator", conflicting_fields=" , ")


def test_pipeline_groups_counterparties_running_more_than_one_thing(ledger):
    """L37: one organiser, a closed written application and an open contest a month later."""
    ledger.investor("ys-vibecode30", "VibeCode30", organiser="yourstory", status="screened-out",
                    deadline="2026-08-31", deadline_source="press", submission="form")
    ledger.investor("ys-30secondsparks", "30SecondSparks", organiser="yourstory", status="cold",
                    deadline="2026-10-02", deadline_source="social", submission="dm")
    ledger.investor("acme-vc", "Acme Ventures", status="cold")

    shared = ledger.pipeline()["shared_organisers"]
    assert set(shared) == {"yourstory"}
    assert [r["id"] for r in shared["yourstory"]] == ["ys-vibecode30", "ys-30secondsparks"]
    # the two sit in different status groups, which is exactly why reading one alone misleads
    assert shared["yourstory"][0]["status"] != shared["yourstory"][1]["status"]


def test_an_organiser_with_one_record_is_not_grouped(ledger):
    ledger.investor("solo-acc", "Solo Accelerator", organiser="solo-org", status="cold")
    assert ledger.pipeline()["shared_organisers"] == {}
