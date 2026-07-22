import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ledger import Ledger, compute_ticket_hash


def test_same_ticket_hashes_identically():
    ticket = {"ticket_id": "TCK-1", "requester_email": "a@b.com", "subject": "s", "body": "b"}
    assert compute_ticket_hash(ticket) == compute_ticket_hash(dict(ticket))


def test_different_tickets_hash_differently():
    t1 = {"ticket_id": "TCK-1", "requester_email": "a@b.com", "subject": "s", "body": "b"}
    t2 = {"ticket_id": "TCK-2", "requester_email": "a@b.com", "subject": "s", "body": "b"}
    assert compute_ticket_hash(t1) != compute_ticket_hash(t2)


def test_ledger_run_twice_processes_once(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ticket_hash = "abc123"

    ledger1 = Ledger(ledger_path)
    assert not ledger1.has_seen(ticket_hash)
    ledger1.record(ticket_hash, "TCK-1", "processed")

    # Simulate a second run: fresh Ledger instance reading the same file.
    ledger2 = Ledger(ledger_path)
    assert ledger2.has_seen(ticket_hash)


def test_ledger_persists_across_instances(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    Ledger(ledger_path).record("hash1", "TCK-1", "processed")
    Ledger(ledger_path).record("hash2", "TCK-2", "processed")

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
