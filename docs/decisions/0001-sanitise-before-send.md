# ADR 0001: Sanitise PII before any data reaches the LLM

## Status

Accepted

## Context

This pipeline processes helpdesk tickets that generally will contain names,
emails, and phone numbers. Sending raw PII to a third-party LLM's API is
a governance risk in any regulated environment (utilities, health,
government), regardless of that provider's own data-handling guidelines.
The safest process is to never let the data leave the machine in the
first place.

## Decision

`src/sanitiser.py` runs synchronously in process, before `src/agent.py`
is ever called. Structured fields (name, email, phone) are fully
replaced with placeholders; free-text fields (subject, body) are swept
with regex + a known-names list to catch PII embedded inline. The
resulting redaction map is held only in memory / local files and is never
logged into the audit trail, and is explicitly excluded via `.gitignore`.

## Consequences

- The LLM only ever sees placeholder tokens like `[NAME_1]`, `[EMAIL_1]`.
- Re-identification (mapping a placeholder back to a real value) can
  only happen locally by whoever ran the pipeline, making certain it's structurally
  impossible for the LLM provider have the access to do it.
- Trade-off: regex + known-names redaction is deliberately conservative
  and will occasionally over-redact (e.g. a common word matching a
  known first name). That's an acceptable false-positive rate for a
  PoC; a production system would likely add an NER model, Entra ID integration or a HR
  directory for better precision, without changing this ADR's core decision.
