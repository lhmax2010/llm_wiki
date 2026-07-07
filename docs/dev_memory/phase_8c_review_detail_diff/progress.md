# Phase 8c - Web Review Detail + Diff / Progress

## 2026-07-07

Implemented the reviewer-only detail read surface for pending review items.

Backend:

- Added `ReviewDetail` and `get_review_detail()` in `review/service.py`.
- Detail reads only `staging/<KB-id>.md` through the existing P5 safe path and
  validation helpers.
- Detail classifies update proposals from audit metadata
  (`operation=propose_update`), the same source of truth used by P8 republish
  and PR #12 reject-update.
- Update diff is computed live from current published entry vs current staging
  proposal. It does not trust caller-supplied diff data and does not read a
  historical diff from audit.
- Extracted `changed_fields_between()` into `governed_api.diff` and reused it
  from P2 middleware so proposal classification and review detail use the same
  changed-field semantics.
- Added `GET /api/review/{entry_id}` and `WebReviewService.review_detail_for_web()`.
- Detail endpoint reuses the P8b queue permission gate. Unknown, reader, and
  contributor users fail closed.
- P5 approve/reject/republish transition logic was not changed.

Frontend:

- Review queue items are selectable.
- The selected item opens a detail panel with full staging proposal content:
  body, evidence, related, source refs, and metadata.
- Update proposals show current published vs proposal comparison and changed
  field badges.
- Net-new proposals show no diff and display the proposal content for review.

Tests added:

- P5 detail helper:
  - net-new pending detail has no published diff;
  - update diff is current published vs staging proposal;
  - invalid/traversal ids and terminal residue are refused.
- Web API:
  - reviewer can read full pending content;
  - contributor/reader/unknown users are denied through existing permission
    gate;
  - traversal ids and non-staging/terminal residue are refused;
  - update diff reflects current published state.
- Frontend:
  - review detail opens from the queue and renders system-computed update diff.

Codex verification:

- `uv run ruff format . --check`
  - `59 files already formatted`
- `uv run ruff check .`
  - `All checks passed!`
- `uv run mypy core tests governed-api mcp index scripts research review web_api`
  - `Success: no issues found in 59 source files`
- `uv run pytest tests/review/test_service.py tests/web_api/test_app.py -q --no-cov`
  - `72 passed, 1 warning`
- `uv run pytest -q`
  - `228 passed, 1 warning`
  - coverage `88.34%`
- `npm run lint`
  - `tsc --noEmit`
- `npm run test -- --run`
  - `9 passed`
- `npm run build`
  - Vite build passed.

Notes:

- The diff is relative to current published, not proposal-time published. This
  is intentional: reviewers need to know what approving now would change.
- `trust_state`, `updated`, `author`, and `author_type` are normalized out of
  update diff comparison so lifecycle/system metadata does not appear as a
  content change. User-editable fields such as `tags` remain part of the diff.
- The endpoint is still an intranet/tooling endpoint that trusts `X-KB-User`,
  consistent with P8/P8b. It does not introduce real authentication.

R14 follow-up:

- FIX-1【MINOR】: Review detail update diffs no longer include system metadata
  noise from `updated`, `author`, or `author_type`. The proposal side is aligned
  with the current published entry before calling the shared diff helper, the
  same way `trust_state` is aligned.
- Tests now cover the previous blind spot where published/proposal metadata had
  the same hard-coded timestamp. The service and HTTP diff tests set different
  `updated`, `author`, and `author_type` values, change only `body`, and assert
  `changed_fields == ["body"]` / `("body",)`.

R14 TODO:

- Rename or split `_write_user`, carrying forward the P8b naming TODO for read
  review endpoints that still use the write-user header dependency.
- Rename `_require_queue_permission` to reflect that the same permission gate
  now covers queue and detail reads.
- Encode review ids in `getReviewDetail()` before constructing the fetch URL.
- Redact or avoid exposing the literal term `staging` in reviewer-facing Web
  detail/path text if the surface becomes less internal.
