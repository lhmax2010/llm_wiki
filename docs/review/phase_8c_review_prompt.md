# Phase 8c Review Prompt - Web Review Detail + Diff

Review this PR as a medium / medium-high risk read-surface change.

Context:

- Phase 8b added Web review queue and approve/reject buttons.
- Reviewers could only see queue summary fields, so approving was close to
  blind review.
- Phase 8c adds reviewer-only pending detail and update diff.

Primary question:

Does `GET /api/review/{entry_id}` expose only the intended pending staging item
to authorized reviewers, while preserving all P5 review transition guarantees?

## Must-Hold Invariants

1. Reviewer-only fail-closed
   - Detail must use the same reviewer-capable permission gate as the queue.
   - Unknown users, readers, and contributors must be denied.
   - The reviewer identity must come from the existing Web auth boundary
     (`X-KB-User`), not from request body data.

2. Safe staging read
   - The endpoint may read only `kb/staging/<KB-id>.md`.
   - It must validate KB id shape before path construction.
   - It must reuse P5/P7a style path protections:
     source-root resolution, symlink rejection, `is_relative_to`, regular-file
     check, and `trust_state=pending`.
   - It must not expose research, drafts, deprecated, entries-as-detail, or
     arbitrary filesystem paths.

3. Diff correctness
   - Update proposals must be detected from audit metadata
     (`operation=propose_update`), matching P8 republish and PR #12
     reject-update.
   - Diff must be computed live: current published vs current staging proposal.
   - Diff must not trust client-supplied `changed_fields` or audit history.
   - Lifecycle-only state (`pending` vs `published`) should not appear as a
     content change.

4. No transition rewrite
   - The PR must not alter P5 approve/reject/republish/reject-update semantics.
   - Web detail must not manage locks, audit writes, terminal transitions, or
     rollback.

## Attack Cases To Check

- `GET /api/review/KB-2026-0001` as reviewer succeeds for a pending staging item.
- Same request as contributor/reader/unknown is denied.
- Traversal-like ids are rejected.
- A published-only entry is not readable through review detail.
- Deprecated/research/draft content is not reachable through this endpoint.
- Update proposal detail returns current published, proposal, and correct
  changed fields.
- Approve/reject endpoints still delegate to P5 service.

## Files To Inspect

- `review/service.py`
  - `ReviewDetail`
  - `get_review_detail`
- `governed-api/governed_api/diff.py`
- `governed-api/governed_api/middleware.py`
  - changed-field helper reuse
- `web_api/service.py`
  - `WebReviewService.review_detail_for_web`
  - `_review_detail_to_dict`
- `web_api/app.py`
  - `GET /api/review/{entry_id}`
- `tests/review/test_service.py`
- `tests/web_api/test_app.py`
- `web/src/App.tsx`
- `web/src/App.test.tsx`

## Non-Goals

- Do not require a full line-by-line diff engine.
- Do not request maker-checker/self-review changes.
- Do not require real authentication beyond the existing P8/P8b `X-KB-User`
  boundary.
- Do not broaden scope into P5 transition changes.
