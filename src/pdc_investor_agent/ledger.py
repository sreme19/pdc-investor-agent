"""Append-only JSONL ledger for pdc-investor-agent.

Three record kinds — investor, touch, note — all appended to the same file. `investor` records fold
by id (later lines merge onto earlier ones — see `fold()`); `touch` and `note` records are append-only
history per investor and are never folded to a single latest. Folding happens at read time in
`fold()`, never by mutating a written line.

"Investor" is the record's historical name, not its limit: the pipeline also holds accelerators,
sovereign programmes, grant pools and fundraising intermediaries, which is what `entity_kind`
distinguishes. They are kept in one record kind rather than two because `touch` and `note` already
reference an investor id, and a parallel kind would fork that reference into two places to look up.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent.parent / "ledger" / "records.jsonl"

# Overridable so the CLI can be exercised against a throwaway ledger in tests without ever
# touching the real (gitignored) one. Nothing in normal operation sets this.
LEDGER_PATH_ENV = "PIA_LEDGER_PATH"


def default_ledger_path() -> Path:
    override = os.environ.get(LEDGER_PATH_ENV)
    return Path(override) if override else DEFAULT_LEDGER_PATH


VALID_STATUSES = {
    "cold",
    "contacted",
    "meeting",
    "diligence",
    "committed",
    "passed",
    "screened-out",
    "declined",
}

# `passed` and `screened-out` are not the same event and must not be collapsed. `passed` is *they*
# said no, after contact. `screened-out` is *we* ruled them out before ever contacting them —
# eligibility we don't meet, a constraint we can't satisfy, a counterparty that didn't verify.
# Reviewing a pipeline six months on, the difference is the whole story.
PRE_CONTACT_STATUSES = {"cold", "screened-out"}

# What kind of counterparty this is. Half of a fundraise pipeline is not a fund, and the ask, the
# terms and the failure modes differ per kind — an accelerator has eligibility criteria and a
# cohort deadline, an intermediary has a fee structure worth establishing before a deck moves.
VALID_ENTITY_KINDS = {"fund", "angel", "accelerator", "programme", "grant", "intermediary"}

# How an approach is actually made. Recorded because it decides what gets drafted: a form with fixed
# questions is a different artifact from a cold email, and finding out which at drafting time is late.
VALID_SUBMISSIONS = {"form", "email", "dm", "warm-intro", "event", "other"}

# Where the deadline was actually read. A date's *shape* was already validated; its *provenance*
# was not, and provenance is what has twice been wrong (PILOT-LOG.md L35). On 6 Sep the deciding
# deadline existed only in a social-media caption and had already been extended once. On 7 Sep a
# programme's closing date was recoverable only from the organiser's own editorial coverage of its
# own programme — a news article — while the application form stayed live, accepted input, and
# stated no date anywhere.
#
# `first-party-page` and `form-itself` are the counterparty publishing its own date. `press` and
# `social` are somebody reporting it, and the fact that the somebody is the organiser's own
# newsroom does not promote it: L19 says verification is per-field, so "first-party" is a claim
# about where *this field* came from, not about the counterparty's identity.
VALID_DEADLINE_SOURCES = {"first-party-page", "form-itself", "press", "social"}

# A deadline from these is recorded, and read as untrusted. Nothing refuses to write it — the date
# is often the only one there is — but it must never print alongside a verified one unmarked.
UNTRUSTED_DEADLINE_SOURCES = {"press", "social"}

# Whether the submission route was observed open. Distinct from the deadline on purpose: on 7 Sep
# the window had closed a week earlier and the form was still accepting entries, so the founder was
# filling in a form that no longer counted. One fact could not carry both, and the schema had
# nowhere to put the second (PILOT-LOG.md L35).
#
# `unknown` is the honest default and is written, not left blank, for the same reason `rolling` is:
# blank means nobody looked, `unknown` means somebody looked and could not tell.
VALID_SUBMISSION_STATES = {"observed-accepting", "observed-closed", "unknown"}

VALID_CHANNELS = {"email", "linkedin", "warm-intro", "event", "call", "other"}
VALID_DIRECTIONS = {"outbound", "inbound"}
# `sighting` is what a source *claimed*, recorded before anybody checked it. It is deliberately not
# `research`, which means somebody went and verified something. A LinkedIn post saying "we write
# $500k cheques" and a fund's own site saying the same thing are not the same fact, and once they
# are both prose in the same field nothing downstream can tell them apart. See PILOT-LOG.md L6/L19:
# one post implied an immediate deadline that the programme's own site put five months out, and one
# aggregator's cheque size differed from the fund's published figure by roughly 6x.
VALID_NOTE_KINDS = {"research", "meeting", "sighting", "screening", "conflict"}

# `conflict` is for the case L34 found and nothing could record: two of the counterparty's *own*
# pages disagreed about the same field. The organiser published one event on two of its domains
# with two different venues. Neither page is an aggregator, so "if the counterparty does not
# publish it, it is unavailable" has nothing to say — the counterparty published it twice,
# differently. It was resolved by judgement, and the judgement then read like a verification.
# The disagreeing field was a venue, i.e. the thing somebody books a flight against.

# Whether anyone has checked this counterparty against their own published eligibility criteria.
#
# Deliberately a separate field from `status`, not another status value. Status tracks how far a
# relationship has got (cold -> contacted -> meeting); eligibility asks a different question whose
# answer does not change as the relationship moves. Folding one into the other repeats the L7
# mistake — a field carrying two meanings compares across records for neither.
#
# The empty string reads as `unscreened`, the same way an empty status reads as `cold`: a record
# that has never carried a verdict has not been screened, and saying so is the whole point.
VALID_ELIGIBILITY = {"eligible", "ineligible"}
UNSCREENED = "unscreened"

# Statuses where an unscreened record is not a problem worth flagging: the record is already out of
# play, so nobody is about to approach it.
CLOSED_STATUSES = {"screened-out", "passed", "declined"}

# Month precision is allowed on purpose: programmes routinely publish "applications close in
# February 2027" with no day. Forcing YYYY-MM-DD would mean inventing a day that nobody stated.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")

# Fields an investor update carries forward when the update doesn't mention them. A later line is a
# partial update, not a replacement: `pia investor --id x --firm F --status passed` must not blank
# the contact and source that an earlier line established.
_MERGEABLE_FIELDS = (
    "firm",
    "organiser",
    "contact",
    "entity_kind",
    "stage_focus",
    "check_size",
    "source",
    "source_url",
    "submission",
    "submission_state",
    "deadline",
    "deadline_source",
    "conflicting_fields",
    "status",
    "eligibility",
    "eligibility_criterion",
    "note",
)


class LedgerError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise LedgerError(f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}")
    return status


def _check_eligibility(eligibility: str) -> str:
    if eligibility not in VALID_ELIGIBILITY:
        raise LedgerError(
            f"eligibility verdict must be one of {sorted(VALID_ELIGIBILITY)}, got {eligibility!r}. "
            f"{UNSCREENED!r} is the absence of a verdict, not one you can record."
        )
    return eligibility


def _check_entity_kind(entity_kind: str) -> str:
    if entity_kind not in VALID_ENTITY_KINDS:
        raise LedgerError(
            f"entity kind must be one of {sorted(VALID_ENTITY_KINDS)}, got {entity_kind!r}"
        )
    return entity_kind


def _check_submission(submission: str) -> str:
    if submission not in VALID_SUBMISSIONS:
        raise LedgerError(
            f"submission must be one of {sorted(VALID_SUBMISSIONS)}, got {submission!r}"
        )
    return submission


def _check_deadline_source(deadline_source: str) -> str:
    if deadline_source not in VALID_DEADLINE_SOURCES:
        raise LedgerError(
            f"deadline source must be one of {sorted(VALID_DEADLINE_SOURCES)}, got "
            f"{deadline_source!r}. The organiser's own newsroom is 'press', not 'first-party-page'"
        )
    return deadline_source


def _check_submission_state(submission_state: str) -> str:
    if submission_state not in VALID_SUBMISSION_STATES:
        raise LedgerError(
            f"submission state must be one of {sorted(VALID_SUBMISSION_STATES)}, got "
            f"{submission_state!r}"
        )
    return submission_state


def _check_conflicting_fields(conflicting_fields: str) -> str:
    """Field names, comma-separated, that two of the counterparty's own pages disagree about.

    Restricted to fields this record actually has, so a typo cannot mark a field nobody can then
    find. The point of the marker is that a reader sees the untrustworthy field *as* untrustworthy;
    pointing at a field that does not exist defeats that.
    """
    names = [name.strip() for name in conflicting_fields.split(",") if name.strip()]
    if not names:
        raise LedgerError("conflicting fields must name at least one field")
    unknown = [name for name in names if name not in _MERGEABLE_FIELDS]
    if unknown:
        raise LedgerError(
            f"cannot mark unknown field(s) as conflicting: {unknown}. "
            f"Valid: {sorted(_MERGEABLE_FIELDS)}"
        )
    return ",".join(names)


def _check_deadline(deadline: str) -> str:
    """A deadline is either a calendar date or the standing absence of one.

    "rolling" is recorded explicitly rather than left blank, because blank means nobody checked and
    rolling means somebody checked and there is no date. Treating those as the same thing is how a
    cohort close gets missed.
    """
    if deadline == "rolling":
        return deadline
    if not _ISO_DATE.match(deadline):
        raise LedgerError(
            f"deadline must be YYYY-MM-DD, YYYY-MM or 'rolling', got {deadline!r}"
        )
    # `date`, not `datetime`: a deadline is a day on a calendar, not an instant, so there is no
    # timezone to attach. Constructing it also rejects impossible dates like 2027-02-31.
    parts = [int(part) for part in deadline.split("-")]
    try:
        date(parts[0], parts[1], parts[2] if len(parts) == 3 else 1)
    except ValueError as e:
        raise LedgerError(f"deadline is not a real date: {deadline!r}") from e
    return deadline


def _merge_investor(prior: dict | None, incoming: dict) -> dict:
    """Later line wins per field, but only for fields it actually carries."""
    if prior is None:
        return dict(incoming)
    merged = dict(prior)
    merged["ts"] = incoming["ts"]
    for key in _MERGEABLE_FIELDS:
        value = incoming.get(key)
        if value not in (None, ""):
            merged[key] = value
    return merged


@dataclass
class Ledger:
    path: Path = field(default_factory=default_ledger_path)

    def _append(self, record: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    # -- writers -----------------------------------------------------------------

    def investor(
        self,
        id: str,
        firm: str,
        organiser: str = "",
        contact: str = "",
        entity_kind: str = "",
        stage_focus: str = "",
        check_size: str = "",
        source: str = "",
        source_url: str = "",
        submission: str = "",
        submission_state: str = "",
        deadline: str = "",
        deadline_source: str = "",
        conflicting_fields: str = "",
        status: str = "",
        eligibility: str = "",
        eligibility_criterion: str = "",
        note: str = "",
    ) -> dict:
        """Append an investor line. Omitted fields are carried forward from earlier lines by `fold()`.

        `status` defaults to empty rather than "cold" so that an update which doesn't mention status
        leaves the existing one alone. A record that has never carried a status reads as "cold".
        The same holds for `eligibility`, which reads as "unscreened".

        A `deadline` cannot be written without a `deadline_source`. That pairing is the only hard
        new gate here, and it is deliberately at the write: a date with no provenance is exactly
        what shipped twice, and it looked identical to a verified one both times. Existing lines
        predate the field and keep reading fine — `fold()` carries forward whatever is there — so
        the rule binds new writes without rewriting history.
        """
        if status:
            _check_status(status)
        if eligibility:
            _check_eligibility(eligibility)
        if entity_kind:
            _check_entity_kind(entity_kind)
        if submission:
            _check_submission(submission)
        if submission_state:
            _check_submission_state(submission_state)
        if conflicting_fields:
            conflicting_fields = _check_conflicting_fields(conflicting_fields)
        if deadline:
            _check_deadline(deadline)
            if not deadline_source:
                raise LedgerError(
                    f"refusing to write deadline {deadline!r} with no deadline source. "
                    f"Pass one of {sorted(VALID_DEADLINE_SOURCES)} — say where you read it. "
                    "Twice now the deciding date has come from press or social while the "
                    "counterparty's own pages published nothing (PILOT-LOG.md L35)."
                )
        if deadline_source:
            _check_deadline_source(deadline_source)
            if not deadline:
                raise LedgerError(
                    "deadline source given with no deadline — there is nothing for it to source"
                )
        record = {
            "kind": "investor",
            "id": id,
            "ts": _now_iso(),
            "firm": firm,
            "organiser": organiser,
            "contact": contact,
            "entity_kind": entity_kind,
            "stage_focus": stage_focus,
            "check_size": check_size,
            "source": source,
            "source_url": source_url,
            "submission": submission,
            "submission_state": submission_state,
            "deadline": deadline,
            "deadline_source": deadline_source,
            "conflicting_fields": conflicting_fields,
            "status": status,
            "eligibility": eligibility,
            "eligibility_criterion": eligibility_criterion,
            "note": note,
        }
        return self._append(record)

    def deadline_is_trusted(self, investor: dict) -> bool | None:
        """Whether this record's deadline came from the counterparty's own pages.

        `None` means there is no deadline, or it predates `deadline_source` — which is not the same
        as untrusted, and the caller has to say so rather than rounding it to either verdict.
        """
        if not investor.get("deadline"):
            return None
        source = investor.get("deadline_source")
        if not source:
            return None
        return source not in UNTRUSTED_DEADLINE_SOURCES

    def screen(
        self,
        investor_id: str,
        verdict: str,
        criterion: str,
        reason: str,
    ) -> tuple[dict, dict]:
        """Record an eligibility verdict: two lines, the field and the evidence for it.

        Both are required. The pilot's failure was not that verdicts were wrong, it was that they
        lived in someone's head or in loose prose, so nothing could tell a checked record from an
        unchecked one (PILOT-LOG.md L8, L31). A verdict with no criterion is the same problem in a
        new field, so `criterion` and `reason` are not optional.

        `ineligible` also sets `status` to `screened-out`, because they are one event: we looked at
        their published rules and ruled them out before contacting anyone. Leaving the caller to
        keep the two in step by hand is how they drift apart.
        """
        _check_eligibility(verdict)
        if not criterion.strip():
            raise LedgerError("criterion is required — name the published rule that decided it")
        if not reason.strip():
            raise LedgerError("reason is required — a verdict with no evidence is not a verdict")
        investor = self.latest_investor(investor_id)
        if investor is None:
            raise LedgerError(f"no investor with id {investor_id!r} — add it with `pia investor` first")

        record = self.investor(
            investor_id,
            investor.get("firm", ""),
            eligibility=verdict,
            eligibility_criterion=criterion,
            status="screened-out" if verdict == "ineligible" else "",
        )
        note = self.note(investor_id, "screening", reason, next_steps=criterion)
        return record, note

    def touch(
        self,
        investor_id: str,
        channel: str,
        direction: str,
        summary: str,
        note: str = "",
        force_unscreened: bool = False,
    ) -> dict:
        if channel not in VALID_CHANNELS:
            raise LedgerError(f"channel must be one of {sorted(VALID_CHANNELS)}, got {channel!r}")
        if direction not in VALID_DIRECTIONS:
            raise LedgerError(f"direction must be one of {sorted(VALID_DIRECTIONS)}, got {direction!r}")
        investor = self.latest_investor(investor_id)
        if investor is None:
            raise LedgerError(f"no investor with id {investor_id!r} — add it with `pia investor` first")

        # The one hard gate in this CLI, and it is a smoke alarm rather than a lock: by the time an
        # outbound touch is logged the message has already been sent by hand, and nothing in a
        # ledger sits upstream of that. What it does buy is that the mistake surfaces while the
        # conversation is still fresh, at the first moment the tooling is involved at all.
        eligibility = investor.get("eligibility") or UNSCREENED
        if direction == "outbound" and eligibility != "eligible" and not force_unscreened:
            if eligibility == "ineligible":
                detail = (
                    f"{investor_id!r} was screened out as ineligible"
                    + (f" ({investor['eligibility_criterion']})" if investor.get("eligibility_criterion") else "")
                )
            else:
                detail = f"nobody has screened {investor_id!r} against their published criteria"
            raise LedgerError(
                f"refusing to log an outbound touch: {detail}. Run `pia screen --investor "
                f"{investor_id} ...` first, or pass --force-unscreened if this was deliberate."
            )

        record = {
            "kind": "touch",
            "investor_id": investor_id,
            "ts": _now_iso(),
            "channel": channel,
            "direction": direction,
            "summary": summary,
            "note": note,
        }
        # Recorded, not just permitted. An override that leaves no trace is indistinguishable from
        # the gate never having been there.
        if force_unscreened and direction == "outbound" and eligibility != "eligible":
            record["forced_past_eligibility"] = eligibility
        return self._append(record)

    def note(
        self,
        investor_id: str,
        note_kind: str,
        summary: str,
        next_steps: str = "",
    ) -> dict:
        if note_kind not in VALID_NOTE_KINDS:
            raise LedgerError(f"note kind must be one of {sorted(VALID_NOTE_KINDS)}, got {note_kind!r}")
        if self.latest_investor(investor_id) is None:
            raise LedgerError(f"no investor with id {investor_id!r} — add it with `pia investor` first")
        record = {
            "kind": "note",
            "investor_id": investor_id,
            "ts": _now_iso(),
            "note_kind": note_kind,
            "summary": summary,
            "next_steps": next_steps,
        }
        return self._append(record)

    # -- readers -------------------------------------------------------------------

    def latest_investor(self, id: str) -> dict | None:
        """The merged view of one investor across every line written for it."""
        merged: dict | None = None
        for record in self.read_all():
            if record["kind"] == "investor" and record.get("id") == id:
                merged = _merge_investor(merged, record)
        return merged

    def fold(self) -> dict:
        """Investor records merged per id; all touches/notes kept, newest last."""
        investors: dict[str, dict] = {}
        touches: list[dict] = []
        notes: list[dict] = []
        for record in self.read_all():
            if record["kind"] == "investor":
                investors[record["id"]] = _merge_investor(investors.get(record["id"]), record)
            elif record["kind"] == "touch":
                touches.append(record)
            elif record["kind"] == "note":
                notes.append(record)
        touches.sort(key=lambda r: r["ts"])
        notes.sort(key=lambda r: r["ts"])
        return {"investors": investors, "touches": touches, "notes": notes}

    def show(self, id: str) -> dict | None:
        """One investor's whole file: the merged record plus every note and touch, oldest first.

        The reason this exists: without it, picking up an investor logged by an earlier session meant
        re-reading raw ledger lines, so the outreach skill asked the user to paste their own research
        notes back in.
        """
        investor = self.latest_investor(id)
        if investor is None:
            return None
        # Built from file order, not from `fold()`'s two sorted lists. Timestamps are only
        # second-granular, so a note and a touch logged in the same second tie; file order is write
        # order, and a stable sort on `ts` therefore keeps same-second entries in the order they
        # actually happened instead of grouping all touches ahead of all notes.
        history = [
            r
            for r in self.read_all()
            if r["kind"] in ("touch", "note") and r.get("investor_id") == id
        ]
        history.sort(key=lambda r: r["ts"])
        return {"investor": investor, "history": history}

    def pipeline(self) -> dict:
        """Every investor grouped by status, with the most recent touch for each.

        `shared_organisers` holds the counterparties running more than one thing. L37: one organiser
        ran a written application that had already closed and a social contest closing a month
        later, around the same event. Grouped only by status, those are two unrelated rows, and
        reading either one answers "what is open with them?" wrongly. Only organisers with two or
        more records appear, because a single record needs no grouping to be read correctly.
        """
        folded = self.fold()
        last_touch_by_investor: dict[str, dict] = {}
        for t in folded["touches"]:
            last_touch_by_investor[t["investor_id"]] = t
        by_status: dict[str, list[dict]] = {}
        by_organiser: dict[str, list[dict]] = {}
        for investor in folded["investors"].values():
            by_status.setdefault(investor.get("status") or "cold", []).append(investor)
            if investor.get("organiser"):
                by_organiser.setdefault(investor["organiser"], []).append(investor)
        for group in by_status.values():
            group.sort(key=lambda r: r["ts"])
        shared_organisers = {
            organiser: sorted(group, key=lambda r: r["ts"])
            for organiser, group in by_organiser.items()
            if len(group) > 1
        }
        return {
            "by_status": by_status,
            "last_touch_by_investor": last_touch_by_investor,
            "shared_organisers": shared_organisers,
        }
