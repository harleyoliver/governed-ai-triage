# ADR 0003: Mock mode as the CI contract, not the real API

## Status

Accepted

## Context

CI needs to prove the pipeline's logic works on every push, so sanitiser,
ledger, guardrails, routing, and audit logging need to run without requiring
a real Anthropic API key as a GitHub Actions secret, and without the pipeline
becoming flaky, slow, or costly because tests depend on live network
calls to a third-party API.

## Decision

`src/agent.py` defines two classes behind the same interface:
`TriageAgent` (real API calls) and `MockTriageAgent` (canned responses).
`src/pipeline.py --mock` runs the entire flow using the mock agent.
`.github/workflows/ci.yml` runs lint, the full pytest suite, and a
`--mock` pipeline run on every push. No `ANTHROPIC_API_KEY` is ever
referenced in CI.

## Consequences

- CI is fast, deterministic, and free to run on every commit.
- CI proves the _pipeline's_ correctness (routing logic, idempotency,
  audit completeness) but it doesn't prove prompt quality or
  real-model output accuracy. That's a known, deliberate gap: prompt
  quality is validated manually against the real API not automated in this PoC.
- Because the interface (`classify(redacted_ticket) -> AgentResult`) is
  shared, swapping mock for real is a one-flag change (`--mock` on/off)
  with zero code changes elsewhere in the pipeline.
