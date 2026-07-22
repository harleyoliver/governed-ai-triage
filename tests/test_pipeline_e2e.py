import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from pipeline import load_config, run_pipeline


@pytest.fixture
def isolated_config(tmp_path):
    """Run the pipeline against a temp copy of config so tests never touch
    the real audit/ledger files or data/review_queue|auto_resolved."""
    config = load_config("config.yaml")
    config["ledger"]["path"] = str(tmp_path / "ledger.jsonl")
    config["audit"]["path"] = str(tmp_path / "audit_log.jsonl")
    config["paths"]["review_queue"] = str(tmp_path / "review_queue")
    config["paths"]["auto_resolved"] = str(tmp_path / "auto_resolved")
    return config


def test_mock_end_to_end_run_processes_all_tickets(isolated_config):
    summary = run_pipeline(isolated_config, mock=True)
    assert summary["processed"] == 13
    assert summary["skipped_duplicate"] == 0
    assert summary["review_queue"] + summary["auto_resolved"] == 13


def test_rerun_skips_already_processed_tickets(isolated_config):
    run_pipeline(isolated_config, mock=True)
    second_run = run_pipeline(isolated_config, mock=True)
    assert second_run["processed"] == 0
    assert second_run["skipped_duplicate"] == 13


def test_known_urgent_ticket_lands_in_review_queue(isolated_config):
    run_pipeline(isolated_config, mock=True)
    review_files = list(Path(isolated_config["paths"]["review_queue"]).glob("*.json"))
    review_ids = {json.loads(p.read_text())["ticket_id"] for p in review_files}
    assert "TCK-1011" in review_ids  # urgent finance outage, must be reviewed


def test_audit_log_has_entry_for_every_stage(isolated_config):
    run_pipeline(isolated_config, mock=True)
    lines = Path(isolated_config["audit"]["path"]).read_text().strip().splitlines()
    stages = {json.loads(line)["stage"] for line in lines}
    assert {"sanitise", "classify", "route"}.issubset(stages)
