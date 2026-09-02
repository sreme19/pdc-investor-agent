"""Append-only JSONL ledger for pdc-investor-agent.

Three record kinds — investor, touch, note — all appended to the same file. `investor` records fold
by id (latest line wins for status/contact fields); `touch` and `note` records are append-only history
per investor and are never folded to a single latest. Folding happens at read time in `fold()`, never
by mutating a written line.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent.parent / "ledger" / "records.jsonl"

VALID_STATUSES = {"cold", "contacted", "meeting", "diligence", "committed", "passed", "declined"}
VALID_CHANNELS = {"email", "linkedin", "warm-intro", "event", "call", "other"}
VALID_DIRECTIONS = {"outbound", "inbound"}
VALID_NOTE_KINDS = {"research", "meeting"}


class LedgerError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise LedgerError(f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}")
    return status


@dataclass
class Ledger:
    path: Path = field(default_factory=lambda: DEFAULT_LEDGER_PATH)

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
        contact: str = "",
        stage_focus: str = "",
        check_size: str = "",
        source: str = "",
        status: str = "cold",
        note: str = "",
    ) -> dict:
        _check_status(status)
        record = {
            "kind": "investor",
            "id": id,
            "ts": _now_iso(),
            "firm": firm,
            "contact": contact,
            "stage_focus": stage_focus,
            "check_size": check_size,
            "source": source,
            "status": status,
            "note": note,
        }
        return self._append(record)

    def touch(
        self,
        investor_id: str,
        channel: str,
        direction: str,
        summary: str,
        note: str = "",
    ) -> dict:
        if channel not in VALID_CHANNELS:
            raise LedgerError(f"channel must be one of {sorted(VALID_CHANNELS)}, got {channel!r}")
        if direction not in VALID_DIRECTIONS:
            raise LedgerError(f"direction must be one of {sorted(VALID_DIRECTIONS)}, got {direction!r}")
        if self.latest_investor(investor_id) is None:
            raise LedgerError(f"no investor with id {investor_id!r} — add it with `pia investor` first")
        record = {
            "kind": "touch",
            "investor_id": investor_id,
            "ts": _now_iso(),
            "channel": channel,
            "direction": direction,
            "summary": summary,
            "note": note,
        }
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
        matches = [r for r in self.read_all() if r["kind"] == "investor" and r.get("id") == id]
        if not matches:
            return None
        return matches[-1]  # file order is append order — last match is the latest

    def fold(self) -> dict:
        """Latest line per id for investor records; all touches/notes kept, newest last."""
        investors: dict[str, dict] = {}
        touches: list[dict] = []
        notes: list[dict] = []
        for record in self.read_all():
            if record["kind"] == "investor":
                investors[record["id"]] = record
            elif record["kind"] == "touch":
                touches.append(record)
            elif record["kind"] == "note":
                notes.append(record)
        touches.sort(key=lambda r: r["ts"])
        notes.sort(key=lambda r: r["ts"])
        return {"investors": investors, "touches": touches, "notes": notes}

    def pipeline(self) -> dict:
        """Every investor grouped by status, with the most recent touch for each."""
        folded = self.fold()
        last_touch_by_investor: dict[str, dict] = {}
        for t in folded["touches"]:
            last_touch_by_investor[t["investor_id"]] = t
        by_status: dict[str, list[dict]] = {}
        for investor in folded["investors"].values():
            by_status.setdefault(investor["status"], []).append(investor)
        for group in by_status.values():
            group.sort(key=lambda r: r["ts"])
        return {"by_status": by_status, "last_touch_by_investor": last_touch_by_investor}
