# Governance

This document describes the data handling policy, human-in-the-loop
rationale, and explicit boundaries for `governed-ai-triage`. It exists
because a triage system touching real support tickets is a compliance
surface and not just a feature. This file is what I'd hand to a
governance review before this went anywhere near production data.

## Data handling policy

1. **Raw ticket content never leaves the local process.** PII
   (names, emails, phone numbers) is redacted by `src/sanitiser.py`
   _before_ anything is sent to the Claude API. Only the redacted
   ticket is transmitted.
2. **The redaction map is local only.** It maps placeholders like
   `[NAME_1]` back to real values, lives only in memory during a run,
   and is never written to disk, never logged, and never committed.
3. **The audit log contains no PII.** Every audit entry references
   tickets by their content hash and redacted fields only.
4. **Mock data only in this repo.** Every file in `data/inbox/`
   is fabricated for demonstration purposes. No real person's data
   has been used to build or test this system.

## Human-in-the-loop rationale

The agent (`src/agent.py`) never has the final word. `src/guardrails.py`
routes every classification through policy checks and anything that
fails those checks goes to `data/review_queue/` for a human to
approve, reject, or edit via `src/review.py`. A ticket is routed to
human review if **any** of the following are true:

- Model confidence is below the configured threshold (default 0.75)
- Priority is `urgent`
- The model raised any `risk_flags` at all (e.g. possible security
  incident, ambiguous request, financial impact)

This is a deliberately conservative policy: it would rather route
to a human than let a low confidence or high stakes classification
auto-resolve without someone taking a look at it. Thresholds live in
`config.yaml`, specifically so a non-technical governance lead can
review and adjust the policy without needing to read Python.

## What this system is NOT allowed to do

- **It doesn't take action on tickets.** It classifies and drafts a
  _suggested_ response; it never sends an email, closes a ticket, or
  contacts a requester. Every resolved item is still a proposal
  sitting in `data/auto_resolved/` and not an executed action.
- **It doesn't retain or reconstruct PII server-side.** The system
  prompt (`prompts/triage_v1.md`) explicitly instructs the model not
  to attempt to infer real values behind redaction placeholders.
- **It doesn't run without an audit trail.** Every stage writes an
  append-only entry into `audit/audit_log.jsonl`. There is no code path
  that skips logging.
- **It doesn't silently reprocess tickets.** The content-hash ledger
  is checked before any model call so a ticket that's already seen is always
  skipped and logged as a duplicate and never reprocessed.
- **It's not a substitute for a incident response process.** Tickets
  flagged `possible_security_incident` are routed to a person and
  not handled with AI. This system is built to handle triages, not respond
  to security incidents using AI tooling.
