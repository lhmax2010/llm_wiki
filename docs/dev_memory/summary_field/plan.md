# Summary Field Plan

## Risk

Low-medium. This adds an optional content field and search weighting across
schema, write DTOs, MCP payloads, Web UI, and skills. It does not alter P5
review transitions, audit, locks, trust-state routing, or claim-type governance.

## Contract

- `summary` is optional and defaults to an empty string.
- `summary` is one sentence, at most 200 characters after whitespace
  normalization.
- `title` remains the short label; `summary` is the richer one-line conclusion,
  root cause, or usage condition.
- `summary` is content/provenance context like `title` and `body`, not
  evidence. It must not upgrade `claim_type` or affect evidence mapping.
- Old entries without `summary` remain valid. No backfill is performed.

## Implementation Plan

- Add `summary` to `Entry` and `EntryUpdate`.
- Normalize leading/trailing whitespace and newlines to single spaces before
  enforcing the length limit.
- Add `summary` to P2 light content fields so propose_update does not treat it
  as an unknown heavy field.
- Add `summary` to search text and score it at +8, below title (+10) and above
  error_codes (+5).
- Prefer `summary` as the search snippet when it exists or matches.
- Add Web create/edit field and payload support while keeping PATCH free of
  `entry_type`.
- Let MCP propose payloads pass `summary` through the existing governed
  pipeline.
- Update ingest/whisper skills so the agent drafts `summary` and shows it for
  human confirmation before propose.

## Explicit Non-Goals

- No automatic LLM generation inside the KB.
- No historical backfill.
- No vector/semantic search implementation yet.
- No changes to P5 review or publish semantics.
