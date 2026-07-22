"""
Human review checkpoint

Lists items in the review queue, lets a human approve/reject/edit each
one, and writes the decision back into the audit log.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from audit import AuditLog  # noqa: E402


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_queue(review_queue: Path) -> list[Path]:
    return sorted(review_queue.glob("*.json"))


def review_item(item_path: Path) -> dict:
    return json.loads(item_path.read_text(encoding="utf-8"))


def print_item(record: dict) -> None:
    print("-" * 60)
    print(f"Ticket:   {record['ticket_id']}")
    print(f"Category: {record['agent_output']['category']}")
    print(f"Priority: {record['agent_output']['priority']}")
    print(f"Confidence: {record['agent_output']['confidence']}")
    print(f"Risk flags: {record['agent_output']['risk_flags']}")
    print(f"Reasons routed to review: {record['routing']['reasons']}")
    print(f"Suggested response: {record['agent_output']['suggested_response']}")
    print("-" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review checkpoint for queued tickets")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    review_queue = Path(config["paths"]["review_queue"])
    auto_resolved = Path(config["paths"]["auto_resolved"])
    audit = AuditLog(config["audit"]["path"])

    items = list_queue(review_queue)
    if not items:
        print("Review queue is empty.")
        return

    print(f"{len(items)} item(s) awaiting review.\n")

    for item_path in items:
        record = review_item(item_path)
        print_item(record)
        choice = input("Approve / Reject / Edit response / Skip? [a/r/e/s]: ").strip().lower()

        if choice == "s":
            continue

        if choice == "a":
            shutil.move(str(item_path), auto_resolved / item_path.name)
            audit.log(ticket_hash=record["ticket_hash"], ticket_id=record["ticket_id"],
                       stage="human_review", decision="approved")
            print("Approved -> moved to auto_resolved.\n")

        elif choice == "r":
            audit.log(ticket_hash=record["ticket_hash"], ticket_id=record["ticket_id"],
                       stage="human_review", decision="rejected")
            print("Rejected -> left in review_queue for follow-up.\n")

        elif choice == "e":
            new_response = input("New suggested response: ").strip()
            record["agent_output"]["suggested_response"] = new_response
            record["human_edited"] = True
            item_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            shutil.move(str(item_path), auto_resolved / item_path.name)
            audit.log(ticket_hash=record["ticket_hash"], ticket_id=record["ticket_id"],
                       stage="human_review", decision="edited_and_approved")
            print("Edited and approved -> moved to auto_resolved.\n")

        else:
            print("Unrecognised input, skipping.\n")


if __name__ == "__main__":
    main()
