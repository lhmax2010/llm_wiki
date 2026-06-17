# Phase 8b - Web Review UI / Progress

## Key Decisions

- Decision: Phase 8b is a separate high-risk Web write surface.
  - It exposes review queue and approve/reject through HTTP and React.
  - It uses the same review strength as Phase 8: Claude + ChatGPT + Kimi +
    Codex HTTP attack-surface smoke.

- Decision: Web review is a thin wrapper over Phase 5 service.
  - `WebReviewService.review_queue_for_web()` delegates to
    `list_review_queue()`.
  - `approve_from_web()` delegates to `approve_staging_entry()`.
  - `reject_from_web()` delegates to `reject_staging_entry()`.
  - The Web layer does not write markdown files, audit logs, indexes, locks, or
    SQLite directly.
  - The Web layer does not set `trust_state`, decide republish/net-new behavior,
    or manage terminal-state checks.

- Decision: queue metadata is reviewer-only.
  - `GET /api/review/queue` requires `X-KB-User`.
  - The user must resolve through `RolesConfig` to admin, `review_light`, or
    `review_heavy`.
  - This keeps staging metadata out of anonymous/reader/contributor views.

- Decision: approve/reject permissions remain Phase 5 owned.
  - Approve requires the P5 combination of `review_light`/`review_heavy` plus
    `publish_entry`.
  - Reject requires the P5 combination of `review_light`/`review_heavy` plus
    `deprecate_entry`.
  - Caller-supplied roles/reviewer names are ignored or rejected by strict DTOs.

- Decision: reuse Phase 8 intranet write guard.
  - `X-KB-User` remains the V1 intranet trust header, not real auth.
  - `X-KB-Write-Intent: web-edit` and `Content-Type: application/json` are
    required for approve/reject.
  - Real login/session/token auth remains a backlog item before broader rollout.

- Decision: self-review is not blocked in this phase.
  - Current design and Phase 5 service do not require `submitter != reviewer`.
  - Phase 8b keeps pure RBAC so small-team/local operation can approve freshly
    submitted entries.
  - TODO: when there are enough reviewers, add a maker-checker policy as a small
    follow-up: `reviewer != author` for approve, with an explicit admin
    exception if desired.

## Implementation

- Backend:
  - Added `WebReviewDecisionRequest` with strict `extra="forbid"` behavior and
    only optional `note`.
  - Added `WebReviewService` in `web_api/service.py`.
  - Added FastAPI routes:
    - `GET /api/review/queue`
    - `POST /api/review/{entry_id}/approve`
    - `POST /api/review/{entry_id}/reject`
  - Reused existing `_write_user()` and `_require_write_request()` dependencies.
  - Review result responses keep the P5 error/warning shape visible to the
    frontend without exposing local paths.

- Frontend:
  - Added review queue/result types.
  - Added `listReviewQueue`, `approveReviewItem`, and `rejectReviewItem`.
  - Added a minimal review panel in the existing React shell.
  - The same `User` field supplies `X-KB-User`; no reviewer/role field is sent
    in the request body.

- Tests:
  - Backend HTTP tests cover queue permissions, approve/reject success,
    republish through P5, terminal duplicate failure, audit rollback, contributor
    privilege failure, role spoofing, missing write intent, form content type,
    governance-field injection, traversal, and P5 lock behavior.
  - Frontend tests cover review queue loading, approve and reject calls, headers,
    and the absence of reviewer/role/trust-state fields in request bodies.

## R14 Follow-up Fixes

- FIX-1 (MINOR): Web review now redacts P5 review `ApiError` and warning
  messages at the HTTP boundary when they contain path-like text or refer to
  internal storage fields such as `audit_path`, `target_path`, `kb_root`, or
  `staging_residue`.
  - Root cause: Phase 8b correctly delegated to P5, but also forwarded P5
    diagnostic messages verbatim. P5 is a local service and may include absolute
    paths in messages such as terminal conflicts, audit failures, and staging
    cleanup warnings.
  - Fix: `WebReviewService` keeps P5 logic untouched, logs the original P5
    error/warning for local debugging, and returns a generic public message to
    HTTP clients.
  - Tests: added HTTP assertions that terminal conflicts, audit failures, and
    source-cleanup warnings do not leak local paths.

## Backlog Notes

- TODO: ResourceWarning / SQLite connection lifecycle. Review P4/P5 SQLite
  connection ownership together and standardize `closing()` usage where needed.
- TODO: rename `_write_user` or split a `_review_user` dependency. `GET
  /api/review/queue` is a read action but reuses the Phase 8 write identity
  dependency for the current intranet `X-KB-User` boundary.
- TODO: queue visibility is not split by review level. This is acceptable for
  the current reviewer pool, but a future UI can hide heavy items from
  light-only reviewers if the role model needs that separation.

## Verification So Far

- `uv run pytest tests\web_api -q --no-cov` -> `33 passed, 1 warning`
- `uv run pytest tests\review tests\web_api -q --no-cov` -> `57 passed, 1 warning`
- `uv run ruff format . --check` -> `58 files already formatted`
- `uv run ruff check .` -> `All checks passed!`
- `uv run mypy core tests governed-api mcp index scripts research review web_api` ->
  `Success: no issues found in 58 source files`
- `uv run pytest --cov --cov-report=term-missing -q` ->
  `209 passed, 1 warning`; total coverage `92.27%`
- `npm.cmd run lint` -> passed
- `npm.cmd test` -> `6 passed`
- `npm.cmd run build` -> passed

## Review Watchpoints

- Check that no Web review path bypasses P5 service.
- Check that contributor/reader/unknown users cannot see queue or make
  decisions.
- Check that approve/reject cannot be controlled through request body
  governance fields.
- Check that P5 republish, terminal-state, lock, and audit rollback semantics
  still hold.
- Codex smoke should actively try role spoofing, traversal, missing headers,
  form encoding, trust-state injection, contributor approval, and nonexistent
  shortcut publish endpoints.
