"""
PII sanitiser — strips personally identifiable information from a raw
ticket BEFORE it is allowed anywhere near the LLM.

Design intent (see docs/decisions/0001-sanitise-before-send.md):
- Redaction happens synchronously, in-process, before any network call.
- The redaction map (placeholder -> original value) never leaves the
  local machine and is never written into the audit log or committed
  to the repo.
- Redaction is intentionally conservative: known-names list + regex
  patterns for emails and AU phone numbers. False positives (over-
  redacting) are an acceptable trade-off; false negatives are not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Matches common AU phone formats: 04xx xxx xxx, 0x xxxx xxxx, +61 4xx xxx xxx,
# +61 x xxxx xxxx, with optional spaces.
PHONE_PATTERN = re.compile(
    r"(?:\+61\s?[2-478]|0[2-478])[\s-]?\d{4}[\s-]?\d{3,4}"
)

# Known-names redaction: a deliberately simple allow-list approach.
# In production this would be sourced from an HR directory export or
# an NER model; here it's a static list to keep the PoC dependency-free
# and fully deterministic for tests.
KNOWN_FIRST_NAMES = {
    "priya", "marcus", "aisha", "daniel", "grace", "liam", "sophie",
    "chen", "olivia", "ben", "fatima", "james", "nadia", "tom",
}
KNOWN_LAST_NAMES = {
    "natarajan", "webb", "khan", "ferreira", "thompson", "o'connell",
    "mensah", "wei", "marsh", "castillo", "al-rashid", "halloran",
    "popescu", "reilly",
}


@dataclass
class RedactionResult:
    redacted_ticket: dict
    redaction_map: dict = field(default_factory=dict)
    fields_redacted: list[str] = field(default_factory=list)


def _redact_names(text: str, counter: dict) -> str:
    def replace(match: re.Match) -> str:
        word = match.group(0)
        key = word.lower().strip(".,!?")
        if key in KNOWN_FIRST_NAMES or key in KNOWN_LAST_NAMES:
            counter["n"] += 1
            placeholder = f"[NAME_{counter['n']}]"
            counter["map"][placeholder] = word
            return placeholder
        return word

    return re.sub(r"[A-Za-z][A-Za-z'\-]+", replace, text)


def _redact_emails(text: str, counter: dict) -> str:
    def replace(match: re.Match) -> str:
        counter["e"] += 1
        placeholder = f"[EMAIL_{counter['e']}]"
        counter["map"][placeholder] = match.group(0)
        return placeholder

    return EMAIL_PATTERN.sub(replace, text)


def _redact_phones(text: str, counter: dict) -> str:
    def replace(match: re.Match) -> str:
        counter["p"] += 1
        placeholder = f"[PHONE_{counter['p']}]"
        counter["map"][placeholder] = match.group(0)
        return placeholder

    return PHONE_PATTERN.sub(replace, text)


def sanitise_ticket(ticket: dict) -> RedactionResult:
    """
    Redact PII from a raw ticket dict. Fields checked: requester_name,
    requester_email, requester_phone, subject, body.

    Returns a RedactionResult whose `redacted_ticket` is safe to send
    to an LLM, and whose `redaction_map` is for LOCAL USE ONLY (never
    logged, never committed — see .gitignore).
    """
    counter = {"e": 0, "p": 0, "n": 0, "map": {}}
    redacted = dict(ticket)
    fields_redacted: list[str] = []

    # Structured fields: always fully redacted, no partial matching needed.
    if redacted.get("requester_name"):
        counter["n"] += 1
        placeholder = f"[NAME_{counter['n']}]"
        counter["map"][placeholder] = redacted["requester_name"]
        redacted["requester_name"] = placeholder
        fields_redacted.append("requester_name")

    if redacted.get("requester_email"):
        counter["e"] += 1
        placeholder = f"[EMAIL_{counter['e']}]"
        counter["map"][placeholder] = redacted["requester_email"]
        redacted["requester_email"] = placeholder
        fields_redacted.append("requester_email")

    if redacted.get("requester_phone"):
        counter["p"] += 1
        placeholder = f"[PHONE_{counter['p']}]"
        counter["map"][placeholder] = redacted["requester_phone"]
        redacted["requester_phone"] = placeholder
        fields_redacted.append("requester_phone")

    # Free-text fields: regex + known-names sweep, since PII can appear
    # inline (e.g. "call sophie.mensah.personal@gmail.com about it").
    for text_field in ("subject", "body"):
        if redacted.get(text_field):
            original = redacted[text_field]
            step1 = _redact_emails(original, counter)
            step2 = _redact_phones(step1, counter)
            step3 = _redact_names(step2, counter)
            if step3 != original:
                fields_redacted.append(text_field)
            redacted[text_field] = step3

    return RedactionResult(
        redacted_ticket=redacted,
        redaction_map=counter["map"],
        fields_redacted=fields_redacted,
    )
