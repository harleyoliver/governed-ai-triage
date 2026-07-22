import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sanitiser import sanitise_ticket


def test_redacts_structured_fields():
    ticket = {
        "ticket_id": "TCK-9001",
        "requester_name": "Priya Natarajan",
        "requester_email": "priya.natarajan@example-corp.com.au",
        "requester_phone": "+61 412 384 021",
        "subject": "Test subject",
        "body": "Test body with no PII.",
    }
    result = sanitise_ticket(ticket)
    assert result.redacted_ticket["requester_name"] == "[NAME_1]"
    assert result.redacted_ticket["requester_email"].startswith("[EMAIL_")
    assert result.redacted_ticket["requester_phone"].startswith("[PHONE_")
    assert "Priya Natarajan" not in str(result.redacted_ticket)


def test_redacts_pii_embedded_in_body_text():
    ticket = {
        "ticket_id": "TCK-9002",
        "requester_name": "Liam O'Connell",
        "requester_email": "liam.oconnell@example-corp.com.au",
        "requester_phone": "0455 118 902",
        "subject": "New starter",
        "body": "Contact sophie.mensah.personal@gmail.com about Sophie's setup.",
    }
    result = sanitise_ticket(ticket)
    body = result.redacted_ticket["body"]
    assert "sophie.mensah.personal@gmail.com" not in body
    assert "[EMAIL_" in body
    assert "[NAME_" in body  # "Sophie" caught by known-names sweep


def test_redaction_map_is_reversible_locally():
    ticket = {
        "ticket_id": "TCK-9003",
        "requester_name": "Grace Thompson",
        "requester_email": "grace.thompson@example-corp.com.au",
        "requester_phone": "+61 419 552 108",
        "subject": "s",
        "body": "b",
    }
    result = sanitise_ticket(ticket)
    name_placeholder = result.redacted_ticket["requester_name"]
    assert result.redaction_map[name_placeholder] == "Grace Thompson"


def test_no_pii_fields_produces_no_redaction():
    ticket = {"ticket_id": "TCK-9004", "subject": "s", "body": "no personal info here"}
    result = sanitise_ticket(ticket)
    assert result.redaction_map == {}
