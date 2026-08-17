# Summary Field Result

## Final Status

Merged-ready after local implementation and maintainer review.

## What Changed

- Added optional `summary` to `Entry` and `EntryUpdate`.
- `summary` defaults to `""`, is whitespace-normalized to one line, and is
  capped at 200 characters.
- Added `summary` to Web create/edit DTOs and the React editor.
- Kept PATCH payloads free of `entry_type` while allowing `summary`, preserving
  the previous 422 regression fix.
- Added `summary` to MCP proposal flow and handler summaries.
- Added `summary` to P2 `LIGHT_FIELDS`, so summary-only updates are accepted as
  light content changes instead of unknown/heavy fields.
- Added search matching and scoring:
  - `title`: +10
  - `summary`: +8
  - `error_codes`: +5
- Search snippets prefer `summary` when present/matching, then fall back to the
  previous title/body behavior.
- Updated `kb/skills/ingest_skill.md` and
  `kb/skills/whisper_ingest_skill.md` so agents draft `summary` and show it for
  human confirmation before proposing.

## Governance

- `summary` is content, not evidence.
- `summary` does not participate in `claim_type` evidence mapping.
- Regression coverage locks that adding summary does not upgrade a weak claim.
- No old entries were backfilled; missing summary remains backward-compatible.

## Motivation

- Improve search precision.
- Give humans a one-line understanding of an entry without reading the whole
  body.
- Prepare a clean future retrieval unit for semantic/vector search.

## Verification

- `uv run ruff check .` passed.
- `uv run mypy .` passed.
- `uv run pytest` passed: 238 passed, coverage 88.24%.
- `npm.cmd run lint` passed.
- `npm.cmd run test` passed: 10 passed.
- `npm.cmd run build` passed.

## Follow-Ups

- Future semantic/vector search can index `summary` as the primary concise
  retrieval unit.
- No automatic KB-internal LLM summary generation is planned; summaries remain
  agent-drafted and human-confirmed.
