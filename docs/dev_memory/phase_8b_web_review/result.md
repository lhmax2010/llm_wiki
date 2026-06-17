# Phase 8b - Web Review UI / Result

## Current Status

Merged via PR #10. Phase 8b adds the Web review surface for human reviewers:
review queue, approve, and reject. The HTTP layer is a thin delegate over the
Phase 5 review service, so terminal-state checks, per-entry locks, republish
handling, validation, audit, and rollback remain P5-owned.

Four-way high-risk review found no BLOCKER or MAJOR items. One MINOR error
hygiene issue was fixed: P5 review errors and warnings are logged with full
local diagnostics but returned to HTTP clients with path-redacted public
messages.

Checkpoint tag: `checkpoint/phase_8b_web_review`.

## Delivered

- Backend HTTP review API:
  - `GET /api/review/queue`
  - `POST /api/review/{entry_id}/approve`
  - `POST /api/review/{entry_id}/reject`
- Web review security boundaries:
  - queue requires reviewer-capable identity;
  - approve/reject use `X-KB-User` resolved through `RolesConfig`;
  - approve/reject require `X-KB-Write-Intent: web-edit`;
  - approve/reject require JSON requests;
  - strict DTOs accept only optional `note`;
  - contributor/reader/unknown users fail closed;
  - request-body reviewer/role/trust-state spoofing is rejected.
- P5 delegation:
  - approve delegates to `approve_staging_entry()`;
  - reject delegates to `reject_staging_entry()`;
  - queue delegates to `list_review_queue()`;
  - Web layer does not write markdown, audit logs, locks, indexes, or SQLite.
- Frontend:
  - reviewer queue panel;
  - approve/reject buttons;
  - operation result and warning/error feedback.
- R14 MINOR:
  - Web review now redacts P5 path-bearing errors/warnings at the HTTP boundary.
  - Tests cover terminal conflict, audit failure, and staging cleanup warning
    leak paths.

## Verification

- Targeted:
  - `uv run pytest tests\web_api -q --no-cov` -> `33 passed, 1 warning`
  - `uv run pytest tests\review tests\web_api -q --no-cov` ->
    `57 passed, 1 warning`
- Python static checks:
  - `uv run ruff format . --check` -> `58 files already formatted`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts research review web_api` ->
    `Success: no issues found in 58 source files`
- Python tests:
  - `uv run pytest --cov --cov-report=term-missing -q` ->
    `209 passed, 1 warning`
  - Total coverage: `92.27%`
- Frontend:
  - `npm.cmd run lint` -> passed
  - `npm.cmd test` -> `6 passed`
  - `npm.cmd run build` -> passed

## Runtime Notes

- Start backend from repo root:
  - `uv run uvicorn web_api.app:app --host 127.0.0.1 --port 8000`
- Start frontend:
  - `cd web`
  - `npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`
- Visit:
  - `http://127.0.0.1:5174`
- Frontend and backend must run at the same time. The frontend calls `/api/*`,
  and Vite proxies those requests to backend port `8000`.
- After pulling or merging P8b, restart both backend and frontend. Stale
  uvicorn/Vite processes can keep old route tables or proxy behavior.
- Review actions require a configured reviewer. The UI `User` field becomes
  `X-KB-User`, and `config/roles.yaml` must map that user to a role with review
  and publish/deprecate permissions.

## PR And Review

- PR link: https://github.com/lhmax2010/llm_wiki/pull/10
- Review prompt: `docs/review/phase_8b_review_prompt.md`
- Required review:
  - Claude + ChatGPT + Kimi high-risk review.
  - Codex HTTP review attack-surface smoke.

## Remaining Risks / TODO

- `X-KB-User` is an intranet MVP trust header and is forgeable. Real
  token/session authentication is needed before broader rollout.
- Self-review is allowed in Phase 8b under pure RBAC. Future larger teams can
  add a maker-checker rule requiring `reviewer != author`, with an explicit
  admin exception if desired.
- Review P4/P5 SQLite connection lifecycle and standardize `closing()` usage
  where needed.
- Rename `_write_user` or split a `_review_user` dependency; `GET
  /api/review/queue` is reviewer-only but not a write action.
- Revisit queue visibility by review level if light-only reviewers need a
  reduced queue view.
- No research collection UI, P7b graph/chat, or P9 collector in this phase.

## Next Step

- Continue with the next DAG target after Phase 8b checkpoint registration.
