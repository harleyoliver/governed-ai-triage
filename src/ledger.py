"""
Idempotency ledger — content-hash based, append-only JSONL.

Design intent (see docs/decisions/0002-hash-ledger-idempotency.md):
- The hash is computed over the RAW ticket content (stable fields only),
  not over anything time-dependent, so re-running the pipeline against
  the same input never reprocesses a ticket twice.
- The ledger is the single source of truth for "have we seen this
  before" guardrails, agent calls, and audit logging all check it
  before doing any work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

# Fields that define ticket identity for hashing. Deliberately excludes
# nothing time-dependent is included here since submitted_at is stable
# per-ticket, but if this pipeline ever ingests live/mutable tickets,
# this is where to revisit.
HASH_FIELDS = ("ticket_id", "requester_email", "subject", "body")


def compute_ticket_hash(ticket: dict) -> str:
    payload = "|".join(str(ticket.get(f, "")) for f in HASH_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class LedgerEntry:
    ticket_hash: str
    ticket_id: str
    status: str  # "processed" | "skipped_duplicate"


class Ledger:
    """
    Append-only JSONL ledger. One line per ticket ever seen.
    Safe to call `has_seen` / `record` repeatedly across runs.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                self._seen.add(entry["ticket_hash"])

    def has_seen(self, ticket_hash: str) -> bool:
        return ticket_hash in self._seen

    def record(self, ticket_hash: str, ticket_id: str, status: str) -> None:
        entry = LedgerEntry(ticket_hash=ticket_hash, ticket_id=ticket_id, status=status)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__) + "\n")
        self._seen.add(ticket_hash)
