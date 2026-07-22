"""
Append JSONL audit log.

Every pipeline action writes: sanitisation, ledger checks,
model calls (with token counts), routing decisions, and
later, human review decisions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **fields) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat()}
        entry.update(fields)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
