import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from guardrails import route

CONFIG = {
    "confidence_threshold": 0.75,
    "always_review_priorities": ["urgent"],
    "route_on_any_risk_flag": True,
}


def test_low_confidence_routes_to_review():
    output = {"confidence": 0.4, "priority": "low", "risk_flags": []}
    decision = route(output, CONFIG)
    assert decision.destination == "review_queue"


def test_urgent_priority_always_routes_to_review_even_with_high_confidence():
    output = {"confidence": 0.99, "priority": "urgent", "risk_flags": []}
    decision = route(output, CONFIG)
    assert decision.destination == "review_queue"


def test_any_risk_flag_routes_to_review():
    output = {"confidence": 0.95, "priority": "low", "risk_flags": ["ambiguous_request"]}
    decision = route(output, CONFIG)
    assert decision.destination == "review_queue"


def test_high_confidence_low_priority_no_flags_auto_resolves():
    output = {"confidence": 0.9, "priority": "low", "risk_flags": []}
    decision = route(output, CONFIG)
    assert decision.destination == "auto_resolved"


def test_reasons_are_populated_on_review():
    output = {"confidence": 0.3, "priority": "urgent", "risk_flags": ["financial_impact"]}
    decision = route(output, CONFIG)
    assert len(decision.reasons) == 3  # confidence + priority + risk flag, all three trip
