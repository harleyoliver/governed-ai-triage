"""
Ingest adapter for governed-ai-triage.

Normalizes tickets from any source (local JSON inbox, JIRA) into the exact dict shape sanitiser.sanitise_ticket() expects: ticket_id, requester_name, requester_email, requester_phone, subject, body.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jira_client import JiraClient


def load_local_tickets(inbox: Path) -> list[dict[str, Any]]:
    tickets = []
    for ticket_path in sorted(inbox.glob("*.json")):
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
        ticket.setdefault("ticket_id", ticket_path.stem)
        tickets.append(ticket)
    return tickets


def load_jira_tickets(config: dict[str, Any], mock: bool) -> list[dict[str, Any]]:
    jira_cfg = config.get("jira", {})
    client = JiraClient(base_url=jira_cfg.get("base_url"), mock=mock)
    raw_tickets = client.fetch_tickets(
        jql=jira_cfg.get("jql", ""),
        max_results=jira_cfg.get("max_results", 15),
    )
    return [
        {
            "ticket_id": t.key,
            "requester_name": t.reporter_name,
            "requester_email": t.reporter_email,
            "requester_phone": "",  # JIRA reporter has no phone field; any phone in the description is caught by the body regex
            "subject": t.summary,
            "body": t.description,
        }
        for t in raw_tickets
    ]


def load_tickets(
    source: str, config: dict[str, Any], mock: bool, inbox: Path | None = None
) -> list[dict[str, Any]]:
    if source == "local":
        return load_local_tickets(inbox or Path(config["paths"]["inbox"]))
    if source == "jira":
        return load_jira_tickets(config, mock)
    raise ValueError(f"Unknown ticket source: {source}")