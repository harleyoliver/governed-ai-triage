# ADR 0004: JIRA integration is mock-first, and uses Basic Auth via API token

## Status

Accepted

## Context

The pipeline needed a real world ticket source beyond what's in the local
`data/inbox/*.json`, I decided the most likely case would be using JIRA Cloud,
writing the routing decision back onto the originating ticket ( with a comment, label, and a status).
Two design questions were driven from the existing patterns in this
repo (ADR 0002, ADR 0003): how do you develop and test a live-API integration
without needing a JIRA instance and credentials, and how would you authenticate to JIRA Cloud if
you did have access to those.

## Decision

**Mock-first.** `src/jira_client.py`'s `JiraClient` takes a `mock: bool` flag
that governs every method, not just the fetch. In mock mode `fetch_tickets()`
reads `data/jira_mock/tickets.json` instead of calling the JIRA REST API,
and `add_comment()`/`add_label()`/`transition_issue()` gets logged in
`data/jira_mock/write_log.jsonl` instead of making an API request to JIRA.
This mirrors `MockTriageAgent` in `src/agent.py` (ADR 0003): the same interface,
a boolean switch with no API calls. It means `--source jira --mock` exercises
the full path in CI with no credentials required, the same way `--mock` already does
for the Claude API.

**Basic Auth via API token.** JIRA Cloud's REST API v3 supports
both Basic Auth (email + API token) and OAuth 2.0 (3LO). This integration
uses Basic Auth: `JIRA_EMAIL` + `JIRA_API_TOKEN` read from environment
variables (`.env`, following the same pattern as `ANTHROPIC_API_KEY`), base64-
encoded into an `Authorization: Basic` header.

## Consequences

- `python src/pipeline.py --source jira --mock` and `python src/review.py
--mock` both run without credentials, and CI exercises both the local and
  JIRA mock paths for every push (`.github/workflows/ci.yml`).
- Switching to a live JIRA instance only requires `JIRA_BASE_URL`, `JIRA_EMAIL`, and
  `JIRA_API_TOKEN` in `.env` and dropping `--mock` tag.
- `JiraClient.__init__` fails fast and raises `JiraClientError` if live mode
  is requested without all three credentials set.
- Trade-off: Basic Auth via a long-lived API token means the token itself is
  the entire security boundary, if this integration were ever offered to other
  organisations rather than run against one team's own JIRA project, this decision
  would need revisiting in favour of OAuth 2.0.
