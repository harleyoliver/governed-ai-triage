"""
Guardrail routing - decides human-review vs auto-resolve.

Design intent: this is deliberately a pure function over the agent's
structured output and config.yaml thresholds, with no side effects and
no model calls, so it's unit-testable in isolation (tests/test_guardrails.py) 
and auditable by a non-engineer reading the config.yaml alone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutingDecision:
    destination: str  # "review_queue" | "auto_resolved"
    reasons: list[str]


def route(agent_output: dict, guardrail_config: dict) -> RoutingDecision:
    reasons: list[str] = []

    confidence = agent_output.get("confidence", 0)
    priority = agent_output.get("priority", "")
    risk_flags = agent_output.get("risk_flags", []) or []

    threshold = guardrail_config["confidence_threshold"]
    always_review = set(guardrail_config.get("always_review_priorities", []))
    route_on_risk = guardrail_config.get("route_on_any_risk_flag", True)

    if confidence < threshold:
        reasons.append(f"confidence {confidence} below threshold {threshold}")

    if priority in always_review:
        reasons.append(f"priority '{priority}' always routes to review")

    if route_on_risk and risk_flags:
        reasons.append(f"risk_flags present: {risk_flags}")

    if reasons:
        return RoutingDecision(destination="review_queue", reasons=reasons)

    return RoutingDecision(destination="auto_resolved", reasons=["passed all guardrail checks"])
