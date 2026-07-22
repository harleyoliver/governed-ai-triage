# ADR 0002: Content-hash ledger for idempotent processing

## Status

Accepted

## Context

Ticket-triage pipelines can get re-run, usually because of a crash,
a config change, or just re-running the same batch by mistake.
Re-processing a ticket that's already been classified means:
a duplicate (and potentoally costly) model call, a duplicate entry in
`review_queue` or `auto_resolved`, and a misleading audit trail that
looks like the ticket was handled twice.

## Decision

Every ticket's identity is defined as a SHA-256 hash over a fixed set
of stable fields (see `HASH_FIELDS` in `src/ledger.py`).
Before any sanitisation or model call, the pipeline checks this hash
against an append-only JSONL ledger. If it's already there, the ticket
is skipped and the skip itself is written to the audit log, so "we saw this
and chose not to reprocess it" is just as visible as "we processed it."

## Consequences

- Re-running `python src/pipeline.py --mock` (or the real version)
  against the same `data/inbox/` is always safe, will use zero duplicate
  model calls and zero duplicate output files.
- The ledger is the single source of truth for "have we seen this,"
  checked once, at the top of the pipeline, not re-derived from
  scanning `review_queue`/`auto_resolved` on every run.
- Trade-off: the hash is content-based, not ticket_id-based, so an
  edited ticket with the same ID but different body content is treated
  as a new ticket and reprocessed. That's intentional as content changes
  are exactly the case where re-triage is warranted.
