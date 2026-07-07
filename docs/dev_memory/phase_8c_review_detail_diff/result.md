# Phase 8c - Web Review Detail + Diff / Result

Status: ready for PR review.

Risk: medium, leaning medium-high.

Why: this phase adds a new read surface for unreviewed staging content. It is
not a public/published read like P7a; it exposes pending body, evidence,
related links, source refs, and update proposal diff to reviewers. The endpoint
therefore stays reviewer-only and reuses P5 safe staging reads.

## Delivered

- `GET /api/review/{entry_id}` returns reviewer-only pending proposal detail.
- Net-new proposal detail includes full staging entry content and no diff.
- Update proposal detail includes:
  - current published entry;
  - current staging proposal;
  - `changed_fields` computed live from current published vs proposal.
- Web Review UI lets reviewers click queue items, inspect full content, and see
  update changed-field comparison before approve/reject.
- Shared changed-field helper extracted for P2 middleware and review detail.
- No P5 transition behavior changed.

## Security / Governance Boundaries

- Reviewer-only permission reuses P8b queue gate:
  admin, `review_light`, or `review_heavy`.
- Unknown users, readers, and contributors are denied.
- Detail read only accepts valid KB ids and reads only `staging/<id>.md`.
- Staging read goes through P5 path safety:
  id fullmatch, source-root resolution, symlink rejection, `is_relative_to`,
  regular-file check, and `trust_state=pending` validation.
- Research, drafts, deprecated, and arbitrary paths are not exposed.
- Diff is system-computed; caller-supplied fields are ignored.
- Update proposal classification uses audit `operation=propose_update`, matching
  P8 republish and PR #12 reject-update.

## Verification

Backend:

```text
uv run ruff format . --check
59 files already formatted

uv run ruff check .
All checks passed!

uv run mypy core tests governed-api mcp index scripts research review web_api
Success: no issues found in 59 source files

uv run pytest tests/review/test_service.py tests/web_api/test_app.py -q --no-cov
72 passed, 1 warning

uv run pytest -q
228 passed, 1 warning
Total coverage: 88.34%
```

Frontend:

```text
npm run lint
tsc --noEmit

npm run test -- --run
9 passed

npm run build
vite build completed successfully
```

## Review Focus

- Confirm `GET /api/review/{entry_id}` cannot be used as a general staging or
  path browser.
- Confirm non-reviewers cannot read staging detail.
- Confirm update diff is current published vs current proposal and does not use
  untrusted client/audit diff payload.
- Confirm P5 approve/reject/republish/reject-update transition behavior remains
  untouched.

## Known Follow-Up

- The UI shows field-level/body comparison, not a full line-by-line diff engine.
  This is intentional for Phase 8c and can be improved later if review volume
  warrants it.
