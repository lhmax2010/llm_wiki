# Phase 8c - Web Review Detail + Diff / Plan

## Risk Classification

Risk: medium, leaning medium-high.

Reason: this phase adds a new HTTP read surface for `staging/` pending content.
Unlike P7a published-only reads, staging entries are not public knowledge yet and
may include unreviewed body text, evidence, related links, and source_refs. The
endpoint must be reviewer-only and must reuse existing safe path resolution and
validation. The phase should not alter P5 approve/reject transition semantics.

Planned review strength: Claude + ChatGPT + Codex HTTP attack-surface smoke.
Escalate to Kimi if implementation touches P5 transition logic or broadens
permissions beyond the existing queue boundary.

## Problem

Phase 8b shipped the review queue and approve/reject buttons, but the reviewer
can only see queue metadata: id, title, module, entry type, claim/support,
review level, updated time, and path. The Web UI does not show the pending
entry body, evidence, related entries, source_refs, or update proposal diff.

This creates a governance gap: reviewers can approve or reject without seeing
enough information to judge the proposal.

## Core Boundaries

### Commandment 1: Detail Is Reviewer-Only

- Add `GET /api/review/{entry_id}`.
- Require the same reviewer-capable identity as `GET /api/review/queue`:
  admin, `review_light`, or `review_heavy`.
- Unknown users, readers, and contributors fail closed.
- Continue using the current intranet `X-KB-User` trust header, with the same
  caveat as P8/P8b: this is not real authentication.

### Commandment 2: Safe Staging Read Path

- The endpoint reads only `kb/staging/<id>.md` for the pending proposal.
- It must validate the KB id shape before path construction.
- It must reuse Phase 5 or existing safe read helpers for:
  - source root resolution;
  - directory symlink rejection;
  - `is_relative_to(kb_root)` checks;
  - regular-file checks;
  - `trust_state=pending` validation.
- It must not scan or expose `research/`, `drafts/`, or arbitrary paths.
- It must not create a general staging browser.

### Commandment 3: Diff Is System-Computed

- For update proposals, identify the proposal type from audit metadata
  (`operation=propose_update`), reusing the same source of truth as P5 republish
  and PR #12 reject-update handling.
- Return both:
  - `proposal`: staging pending entry;
  - `published`: current published entry, if this is an update proposal and the
    target still exists.
- Return `changed_fields` computed from the published entry and staging entry.
- Reuse the P2 actual-diff logic or extract it into a small shared helper rather
  than accepting caller-supplied `changed_fields`.
- Do not promise full audit diff history; design says audit V1 does not store
  complete diff. The detail endpoint computes current diff on read.

### Commandment 4: No P5 Transition Rewrite

- Do not rewrite approve/reject/publish/deprecate behavior in Web API.
- Do not manage P5 locks or terminal-state transitions in the Web detail code.
- Do not loosen terminal mutual exclusion, republish, reject-update, symlink, or
  audit rollback behavior.

## API Shape

`GET /api/review/{entry_id}`

Response draft:

```json
{
  "entry_id": "KB-2026-0006",
  "operation": "propose_entry | propose_update | unknown",
  "review_level": "light | heavy",
  "proposal": { "...": "full staging entry JSON" },
  "published": { "...": "full published entry JSON or null" },
  "changed_fields": ["body", "credibility"],
  "diff_available": true
}
```

Notes:

- Net-new proposals return `published: null`, `changed_fields: []`, and
  `diff_available: false`.
- Update proposals with a missing or unreadable published target return a
  sanitized error or a detail response that marks `diff_available: false`; choose
  the safer behavior during implementation after checking P5 expectations.
- Path-like P5 errors must remain redacted at the HTTP boundary, following P8b.

## Frontend

- `ReviewPanel` should let a reviewer select/click a queue item.
- On selection, call `GET /api/review/{id}` with `X-KB-User`.
- Show the pending proposal detail:
  - title/id/module/type/trust/review level/operation;
  - body;
  - evidence;
  - related;
  - source_refs/provenance;
  - signals/tags/errors/log signatures where useful.
- For update proposals, show a compact comparison:
  - changed field badges from `changed_fields`;
  - old vs new values for common fields;
  - body old/new side-by-side or stacked if changed.
- Keep approve/reject buttons next to the detail.
- Do not let the frontend read local files or synthesize governance fields.

## Reuse

- P5 review metadata/read helpers for pending staging entries and update
  proposal classification.
- P8b reviewer permission gate for queue/detail.
- P7a/P4 safe read isolation patterns.
- P2 actual changed-fields logic, ideally through an extracted shared helper.

## Explicitly Out Of Scope

- No research collection UI.
- No collector/P9 batch preview.
- No maker-checker/self-review policy change.
- No P5 approve/reject transition rewrite.
- No complex line-by-line diff engine beyond readable field/body comparison.
- No general staging/drafts/research browser.
- No real authentication replacement for `X-KB-User`.

## File Plan

- `review/service.py`
  - Add read-only review detail data structure and helper, or expose a minimal
    safe helper that reuses existing private path/metadata utilities.
- `governed-api/governed_api/`
  - If needed, extract actual changed-field computation into a small reusable
    helper without changing classification semantics.
- `web_api/service.py`
  - Add `WebReviewService.review_detail_for_web()`.
  - Reuse reviewer permission check and response redaction.
- `web_api/app.py`
  - Add `GET /api/review/{entry_id}`.
- `tests/review/test_service.py`
  - Cover staging detail for net-new and update proposal.
  - Cover traversal/id invalid/research not visible if helper sits in P5.
- `tests/web_api/test_app.py`
  - Cover reviewer-only detail, reader/contributor denial, unknown user denial,
    staging detail success, update diff success, traversal rejection, no
    research leakage, and sanitized errors.
- `web/src/api.ts`, `web/src/types.ts`, `web/src/App.tsx`,
  `web/src/App.test.tsx`, `web/src/styles.css`
  - Add review detail client/types/UI/tests.
- `docs/dev_memory/phase_8c_review_detail_diff/progress.md`
- `docs/dev_memory/phase_8c_review_detail_diff/result.md`
- `docs/review/phase_8c_review_prompt.md`

## Definition Of Done

- Reviewer can open a pending queue item and inspect full proposal content.
- Update proposal detail shows published vs pending and system-computed changed
  fields.
- Non-reviewer users cannot read review detail.
- Detail endpoint cannot read research/drafts/deprecated or arbitrary paths.
- Queue/approve/reject behavior from P8b and P5 remains unchanged.
- P5 PR #12 reject-update behavior remains covered.
- Backend gates pass:
  - ruff format/check;
  - mypy;
  - full pytest;
  - targeted review/web_api tests.
- Frontend gates pass:
  - `npm run lint`;
  - `npm run test`;
  - `npm run build`.
- Codex HTTP smoke covers:
  - reviewer detail success;
  - contributor/reader denial;
  - traversal id rejection;
  - update diff response;
  - research/staging/drafts isolation boundaries;
  - approve/reject still delegate to P5.
