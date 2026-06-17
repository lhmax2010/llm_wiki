# Phase 8 - Web Edit / Result

## Current Status

R14 closure ready. Phase 8 implements the minimal Web edit surface: humans can
propose new entries and propose edits through FastAPI + React, and all writes
run through the Phase 2 Governed API pipeline into `staging/`.

Review found 1 BLOCKER, 1 MAJOR, and 2 MINOR items. All have been fixed with
regression tests.

## Delivered

- Backend HTTP write API:
  - `POST /api/entries`
  - `PATCH /api/entries/{id}`
- Write security boundaries:
  - `X-KB-User` required and resolved through `RolesConfig`;
  - `X-KB-Write-Intent: web-edit` required;
  - JSON-only write requests;
  - strict DTOs reject untrusted governance fields;
  - writes are forced to pending/staging for P8 MVP;
  - research evidence rejection inherited from P6/P1.
- Frontend:
  - minimal create form;
  - minimal edit flow from selected entry;
  - pending/review/error/warning feedback.
- Phase 2 warning propagation fix:
  - `persist` preserves earlier validation warnings so Web users see system downgrades.
- R14 fixes:
  - Web create rebuilds ID allocation state before issuing IDs and `persist()` rejects allocated-id collisions across official ID directories.
  - P5 approve supports system-proven update/republish proposals while net-new duplicate publish and deprecated terminal conflicts still fail.
  - Web writes have an explicit post-review/pre-persist staging invariant.
  - Form-encoded write requests return `415`.

## Verification

- Python static checks:
  - `uv run ruff format . --check; uv run ruff check .` -> `58 files already formatted`; `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts research review web_api` -> `Success: no issues found in 58 source files`
- Python tests:
  - `uv run pytest tests\review tests\web_api tests\governed_api -q --no-cov` -> `89 passed, 1 warning`
  - `uv run pytest --cov --cov-report=term-missing -q` -> `202 passed, 1 warning`
  - Total coverage: `92.01%`
- Frontend:
  - `npm.cmd run lint` -> passed
  - `npm.cmd test` -> `4 passed`
  - `npm.cmd run build` -> passed

## PR And Review

- PR link: https://github.com/lhmax2010/llm_wiki/pull/9
- Review prompt: `docs/review/phase_8_review_prompt.md`
- Required review:
  - Claude + ChatGPT + Kimi high-risk review.
  - Codex HTTP write attack-surface smoke.

## Remaining Risks / TODO

- `X-KB-User` is an intranet MVP trust header and is forgeable. It is not real authentication.
- CSRF protection is minimal and should be replaced by token/session auth before wider rollout.
- P8 rejects duplicate pending proposals for the same entry with `E_DUP`; no merge UI yet.
- No research collection UI, review approve/reject UI, P7b graph/chat, or P9 collector in this phase.

## Next Step

- Run high-risk Phase 8 review and close R14 findings before merge.
