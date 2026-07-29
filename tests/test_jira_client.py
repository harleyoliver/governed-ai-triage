import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from jira_client import JiraClient, JiraClientError


@pytest.fixture
def mock_write_log(monkeypatch, tmp_path):
    """Redirect the mock write-back log to a temp file so tests never touch
    the real data/jira_mock/write_log.jsonl."""
    import jira_client

    log_path = tmp_path / "write_log.jsonl"
    monkeypatch.setattr(jira_client, "MOCK_WRITE_LOG_PATH", log_path)
    return log_path


def read_log(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text().strip().splitlines()]


def test_fetch_mock_returns_fixture_tickets():
    tickets = JiraClient(mock=True).fetch_tickets(jql="", max_results=15)
    assert len(tickets) == 4
    keys = {t.key for t in tickets}
    assert keys == {"HELP-101", "HELP-102", "HELP-103", "HELP-104"}


def test_fetch_mock_normalizes_reporter_fields():
    tickets = JiraClient(mock=True).fetch_tickets(jql="", max_results=15)
    ticket = next(t for t in tickets if t.key == "HELP-101")
    assert ticket.reporter_name == "Jane Doe"
    assert ticket.reporter_email == "jane.doe@example-corp.com.au"
    assert "MFA" in ticket.summary


def test_add_comment_mock_writes_log_entry(mock_write_log):
    JiraClient(mock=True).add_comment("HELP-101", "Looking into this now.")
    entries = read_log(mock_write_log)
    assert entries == [
        {"action": "add_comment", "issue_key": "HELP-101", "text": "Looking into this now."}
    ]


def test_add_label_mock_writes_log_entry(mock_write_log):
    JiraClient(mock=True).add_label("HELP-101", "ai-triaged")
    entries = read_log(mock_write_log)
    assert entries == [
        {"action": "add_label", "issue_key": "HELP-101", "label": "ai-triaged"}
    ]


def test_transition_issue_mock_writes_log_entry(mock_write_log):
    JiraClient(mock=True).transition_issue("HELP-101", "Done")
    entries = read_log(mock_write_log)
    assert entries == [
        {"action": "transition", "issue_key": "HELP-101", "transition": "Done"}
    ]


def test_write_back_calls_append_to_the_same_log(mock_write_log):
    client = JiraClient(mock=True)
    client.add_comment("HELP-101", "Resolved.")
    client.add_label("HELP-101", "ai-triaged")
    client.transition_issue("HELP-101", "Done")
    entries = read_log(mock_write_log)
    assert [e["action"] for e in entries] == ["add_comment", "add_label", "transition"]


def test_live_mode_without_credentials_raises(monkeypatch):
    for var in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(JiraClientError, match="Live mode requires"):
        JiraClient(mock=False, base_url=None, email=None, api_token=None)
