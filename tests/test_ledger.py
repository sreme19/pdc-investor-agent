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
        ledger.touch("does-not-exist", "email", "outbound", "cold intro")


def test_touch_and_note_lifecycle(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "outbound", "sent intro deck")
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")
    ledger.note("acme-vc", "research", "portfolio overlap w/ two competitors", next_steps="ask for warm intro")

    folded = ledger.fold()
    assert len(folded["touches"]) == 1
    assert len(folded["notes"]) == 1
    assert folded["investors"]["acme-vc"]["status"] == "contacted"


def test_pipeline_groups_by_latest_status(ledger):
    ledger.investor("acme-vc", "Acme Ventures", status="cold")
    ledger.touch("acme-vc", "email", "outbound", "sent intro deck")
    ledger.investor("acme-vc", "Acme Ventures", status="contacted")

    pipeline = ledger.pipeline()
    assert "contacted" in pipeline["by_status"]
    assert pipeline["by_status"]["contacted"][0]["id"] == "acme-vc"
    assert "cold" not in pipeline["by_status"]
    assert pipeline["last_touch_by_investor"]["acme-vc"]["channel"] == "email"
