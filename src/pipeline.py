"""
Pipeline orchestrator: ingest -> sanitise -> ledger check -> classify -> route -> audit.

Run modes:
  --mock   uses MockTriageAgent, no API key or network needed.
  (default) uses the real Claude API via TriageAgent, requires ANTHROPIC_API_KEY in .env.

Idempotency: every ticket's content hash is checked against the ledger before any model call is made. Re-running this script against the same data/inbox/ never reprocesses a ticket or duplicates a routing decision.

Ingest source: --source local (default, data/inbox/*.json) or --source jira (pulls from JIRA Cloud via src/ingest.py + src/jira_client.py). Both sources normalize into the same ticket dict shape before sanitisation.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from agent import MockTriageAgent, TriageAgent
from audit import AuditLog
from guardrails import route
from ingest import load_tickets
from ledger import Ledger, compute_ticket_hash
from sanitiser import sanitise_ticket


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_pipeline(
    config: dict, mock: bool = False, source: str = "local", inbox_override: str | None = None
) -> dict:
    """Runs the full pipeline once. Returns a summary dict"""
    paths = config["paths"]
    inbox = Path(inbox_override or paths["inbox"])
    review_queue = Path(paths["review_queue"])
    auto_resolved = Path(paths["auto_resolved"])
    review_queue.mkdir(parents=True, exist_ok=True)
    auto_resolved.mkdir(parents=True, exist_ok=True)

    ledger = Ledger(config["ledger"]["path"])
    audit = AuditLog(config["audit"]["path"])
    agent = MockTriageAgent() if mock else TriageAgent(config)

    summary = {"processed": 0, "skipped_duplicate": 0, "review_queue": 0, "auto_resolved": 0}

    tickets = load_tickets(source=source, config=config, mock=mock, inbox=inbox)
    for ticket in tickets:
        ticket_hash = compute_ticket_hash(ticket)
        ticket_id = ticket.get("ticket_id", ticket_hash[:12])

        if ledger.has_seen(ticket_hash):
            audit.log(ticket_hash=ticket_hash, ticket_id=ticket_id, stage="ledger_check",
                       model=None, decision="skipped_duplicate")
            summary["skipped_duplicate"] += 1
            continue

        redaction = sanitise_ticket(ticket)
        audit.log(ticket_hash=ticket_hash, ticket_id=ticket_id, stage="sanitise",
                   model=None, fields_redacted=redaction.fields_redacted)

        result = agent.classify(redaction.redacted_ticket)
        audit.log(
            ticket_hash=ticket_hash, ticket_id=ticket_id, stage="classify",
            model=result.model, input_tokens=result.input_tokens,
            output_tokens=result.output_tokens, repaired=result.repaired,
            output=result.output,
        )

        decision = route(result.output, config["guardrails"])
        destination_dir = review_queue if decision.destination == "review_queue" else auto_resolved
        output_record = {
            "ticket_id": ticket_id,
            "ticket_hash": ticket_hash,
            "redacted_ticket": redaction.redacted_ticket,
            "agent_output": result.output,
            "routing": {"destination": decision.destination, "reasons": decision.reasons},
        }
        (destination_dir / f"{ticket_id}.json").write_text(
            json.dumps(output_record, indent=2), encoding="utf-8"
        )

        audit.log(ticket_hash=ticket_hash, ticket_id=ticket_id, stage="route",
                   model=None, destination=decision.destination, reasons=decision.reasons)

        ledger.record(ticket_hash, ticket_id, status="processed")
        summary["processed"] += 1
        summary[decision.destination] += 1

    return summary


def reset_run_state(config: dict) -> None:
    """Clears ledger, audit log, and output folders. Used by --reset and by tests."""
    for path_key in (config["ledger"]["path"], config["audit"]["path"]):
        p = Path(path_key)
        if p.exists():
            p.unlink()
    for folder_key in ("review_queue", "auto_resolved"):
        folder = Path(config["paths"][folder_key])
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Governed AI ticket-triage pipeline")
    parser.add_argument(
        "--mock", action="store_true",
        help="Use mock responses, no API key needed"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear ledger/audit/output state before running"
    )
    parser.add_argument(
        "--config",
        default="config.yaml"
    )
    parser.add_argument(
        "--source",
        choices=["local", "jira"],
        default="local",
        help="Where to pull tickets from (default: local inbox)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if args.reset:
        reset_run_state(config)

    summary = run_pipeline(config, mock=args.mock, source=args.source)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()