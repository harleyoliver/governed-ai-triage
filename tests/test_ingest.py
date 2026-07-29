import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from ingest import load_jira_tickets, load_local_tickets, load_tickets

REQUIRED_KEYS = {"ticket_id", "source", "requester_name", "requester_email",
                  "requester_phone", "subject", "body"}


def test_load_local_tickets_normalizes_shape():
    tickets = load_local_tickets(Path("data/inbox"))
    assert len(tickets) == 13
    for ticket in tickets:
        assert REQUIRED_KEYS.issubset(ticket.keys())
        assert ticket["source"] == "local"


def test_load_local_tickets_falls_back_to_filename_stem_for_missing_id(tmp_path):
    (tmp_path / "no_id_ticket.json").write_text(
        '{"subject": "test", "body": "test body"}', encoding="utf-8"
    )
    tickets = load_local_tickets(tmp_path)
    assert tickets[0]["ticket_id"] == "no_id_ticket"


def test_load_jira_tickets_normalizes_shape():
    config = {"jira": {"base_url": None, "jql": "", "max_results": 15}}
    tickets = load_jira_tickets(config, mock=True)
    assert len(tickets) == 4
    for ticket in tickets:
        assert REQUIRED_KEYS.issubset(ticket.keys())
        assert ticket["source"] == "jira"
    ticket_ids = {t["ticket_id"] for t in tickets}
    assert ticket_ids == {"HELP-101", "HELP-102", "HELP-103", "HELP-104"}


def test_load_jira_tickets_leaves_phone_blank_since_jira_has_no_phone_field():
    config = {"jira": {"base_url": None, "jql": "", "max_results": 15}}
    tickets = load_jira_tickets(config, mock=True)
    assert all(t["requester_phone"] == "" for t in tickets)


def test_load_tickets_dispatches_local():
    config = {"paths": {"inbox": "data/inbox"}}
    tickets = load_tickets(source="local", config=config, mock=True)
    assert len(tickets) == 13


def test_load_tickets_dispatches_jira():
    config = {"jira": {"base_url": None, "jql": "", "max_results": 15}}
    tickets = load_tickets(source="jira", config=config, mock=True)
    assert len(tickets) == 4


def test_load_tickets_rejects_unknown_source():
    with pytest.raises(ValueError, match="Unknown ticket source"):
        load_tickets(source="carrier_pigeon", config={}, mock=True)
