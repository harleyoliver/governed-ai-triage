"""
Claude API agent call - structured triage classification.

Design intent:
- Prompt is loaded from prompts/triage_v1.md (versioned, not inlined
  in code) so prompt changes are reviewable with their own version history.
- Strict JSON parsing with a single repair attempt rather than silently guessing at malformed output.
- Retry with backoff on transient API errors only, broken JSON is handled separately via the repair path
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

REQUIRED_KEYS = {"category", "priority", "suggested_response", "confidence", "risk_flags"}


@dataclass
class AgentResult:
    output: dict
    input_tokens: int
    output_tokens: int
    model: str
    repaired: bool = False


def load_prompt(prompt_path: str | Path) -> str:
    """Strip the YAML frontmatter, return only the prompt body sent to the model."""
    text = Path(prompt_path).read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()
    return text.strip()


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response, tolerant of
    accidental prose or code fences around it."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _validate(parsed: dict) -> None:
    missing = REQUIRED_KEYS - parsed.keys()
    if missing:
        raise ValueError(f"Missing required keys: {missing}")
    if not isinstance(parsed["confidence"], (int, float)):
        raise ValueError("confidence must be numeric")
    if not isinstance(parsed["risk_flags"], list):
        raise ValueError("risk_flags must be a list")


class TriageAgent:
    def __init__(self, config: dict, prompt_path: str | Path = "prompts/triage_v1.md"):
        self.config = config
        self.system_prompt = load_prompt(prompt_path)
        self._client = None  # lazy-loaded, so --mock never needs the SDK/key

    def _get_client(self):
        if self._client is None:
            import anthropic  # deferred import: not required in --mock mode

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Copy .env.example to .env and "
                    "add your key, or run the pipeline with --mock."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def classify(self, redacted_ticket: dict) -> AgentResult:
        client = self._get_client()
        model = self.config["model"]["name"]
        max_tokens = self.config["model"]["max_tokens"]
        max_retries = self.config["model"]["max_retries"]
        backoff_base = self.config["model"]["backoff_base_seconds"]

        user_message = json.dumps(redacted_ticket, indent=2)

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=self.system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                raw_text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                try:
                    parsed = _extract_json(raw_text)
                    _validate(parsed)
                    return AgentResult(
                        output=parsed,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        model=model,
                    )
                except (ValueError, json.JSONDecodeError) as parse_error:
                    # Repair path: ask the model to fix its own output.
                    repair_response = client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=(
                            "The previous response was not valid JSON matching "
                            "the required schema. Return ONLY the corrected JSON "
                            "object, no other text."
                        ),
                        messages=[
                            {"role": "user", "content": user_message},
                            {"role": "assistant", "content": raw_text},
                            {"role": "user", "content": f"Fix this error: {parse_error}"},
                        ],
                    )
                    repair_text = "".join(
                        block.text for block in repair_response.content if block.type == "text"
                    )
                    parsed = _extract_json(repair_text)
                    _validate(parsed)
                    return AgentResult(
                        output=parsed,
                        input_tokens=response.usage.input_tokens
                        + repair_response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens
                        + repair_response.usage.output_tokens,
                        model=model,
                        repaired=True,
                    )
            except Exception as exc:  # noqa: BLE001 - transient API/network errors
                last_error = exc
                if attempt < max_retries:
                    time.sleep(backoff_base ** attempt)
                    continue
                raise RuntimeError(
                    f"Agent call failed after {max_retries} attempts: {last_error}"
                ) from last_error

        raise RuntimeError(f"Agent call failed: {last_error}")


class MockTriageAgent:
    """
    Canned responses keyed by ticket_id, so the pipeline, tests, and CI
    all can be run without API keys or network calls.
    """

    _CANNED = {
        "TCK-1001": {"category": "access_request", "priority": "high", "confidence": 0.88,
                     "risk_flags": [],
                     "suggested_response": "We're looking into your shared drive access now and will have it restored before your 2pm deadline."},
        "TCK-1002": {"category": "hardware_request", "priority": "low", "confidence": 0.93,
                     "risk_flags": [],
                     "suggested_response": "Happy to arrange a second monitor — you can collect it from the Geelong office reception any weekday."},
        "TCK-1003": {"category": "technical_fault", "priority": "high", "confidence": 0.81,
                     "risk_flags": ["angry_customer"],
                     "suggested_response": "We're sorry for the delay and frustration this has caused. Escalating your recurring laptop crash to a senior technician today."},
        "TCK-1004": {"category": "technical_fault", "priority": "medium", "confidence": 0.85,
                     "risk_flags": [],
                     "suggested_response": "Thanks for flagging — we'll check the VPN gateway logs for drops this morning and follow up shortly."},
        "TCK-1005": {"category": "general_inquiry", "priority": "low", "confidence": 0.42,
                     "risk_flags": ["ambiguous_request"],
                     "suggested_response": "Thanks for flagging this — could you let us know which dashboard and figures look off so we can look into it?"},
        "TCK-1006": {"category": "access_request", "priority": "medium", "confidence": 0.90,
                     "risk_flags": [],
                     "suggested_response": "Standard access package for the new starter will be provisioned ahead of Monday."},
        "TCK-1007": {"category": "facilities", "priority": "low", "confidence": 0.95,
                     "risk_flags": [],
                     "suggested_response": "Thanks for the heads up — toner replacement has been logged for level 3."},
        "TCK-1008": {"category": "security_incident", "priority": "urgent", "confidence": 0.79,
                     "risk_flags": ["possible_security_incident"],
                     "suggested_response": "Thank you for reporting this immediately. We're locking down the account and investigating the login activity now."},
        "TCK-1009": {"category": "access_request", "priority": "low", "confidence": 0.91,
                     "risk_flags": [],
                     "suggested_response": "Here's the self-service password reset link — resending it to you now."},
        "TCK-1010": {"category": "facilities", "priority": "low", "confidence": 0.87,
                     "risk_flags": [],
                     "suggested_response": "Thanks — actioning the standing desk request from your ergonomic assessment now."},
        "TCK-1011": {"category": "technical_fault", "priority": "urgent", "confidence": 0.93,
                     "risk_flags": ["financial_impact"],
                     "suggested_response": "Treating this as highest priority — engineering is investigating the finance system outage now ahead of the 3pm payment run."},
        "TCK-1012": {"category": "access_request", "priority": "low", "confidence": 0.89,
                     "risk_flags": [],
                     "suggested_response": "Happy to arrange a 3-month Illustrator licence — processing this now."},
        "TCK-1013": {"category": "other", "priority": "low", "confidence": 0.21,
                     "risk_flags": ["ambiguous_request"],
                     "suggested_response": "Thanks for reaching out — could you give us a bit more detail on what you'd like a call about?"},
    }

    def classify(self, redacted_ticket: dict) -> AgentResult:
        ticket_id = redacted_ticket.get("ticket_id", "")
        canned = self._CANNED.get(ticket_id, {
            "category": "other", "priority": "low", "confidence": 0.5,
            "risk_flags": ["ambiguous_request"],
            "suggested_response": "Thanks for your ticket, we'll take a look shortly.",
        })
        return AgentResult(
            output=canned,
            input_tokens=250,
            output_tokens=90,
            model="mock-claude-sonnet-4-6",
        )
