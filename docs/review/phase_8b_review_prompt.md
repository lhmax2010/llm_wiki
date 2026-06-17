# Phase 8b Review Prompt - Web Review UI

## How To Review

Code is on branch `phase/8b-web-review`. Focus on:

- `web_api/app.py`
- `web_api/service.py`
- `review/service.py` only as the delegated Phase 5 boundary
- `tests/web_api/test_app.py`
- `tests/review/test_service.py`
- `web/src/App.tsx`
- `web/src/api.ts`
- `web/src/App.test.tsx`

Design baseline: `docs/design.md` v1.4, especially HTTP API review endpoints,
RBAC/review permissions, Phase 5 staging review, and Phase 8 Web write boundary.

## Background

Phase 8b adds the reviewer Web surface that Phase 8 deliberately left out:

- reviewer sees staging review queue;
- reviewer approves an item into `entries/`;
- reviewer rejects an item into `deprecated/`.

This is a high-risk HTTP write surface. The operation is more privileged than
P8 propose/edit because it controls the release gate.

The head risk: Web review must not become a second review implementation. It
must be an HTTP wrapper around Phase 5 `review.service`.

## Special Checks

### 1. HTTP Review Must Not Bypass Phase 5

Verify:

- `GET /api/review/queue` delegates to `list_review_queue`.
- `POST /api/review/{id}/approve` delegates to `approve_staging_entry`.
- `POST /api/review/{id}/reject` delegates to `reject_staging_entry`.
- Web code does not directly write `kb/entries/`, `kb/staging/`,
  `kb/deprecated/`, audit logs, locks, or SQLite.
- Web code does not set `trust_state`, decide republish/net-new semantics, or
  manage per-entry locks.

### 2. Reviewer Permissions Are Stronger Than Propose

Verify:

- Queue is not anonymous and not visible to reader/contributor.
- Queue requires admin, `review_light`, or `review_heavy`.
- Approve uses Phase 5 checks:
  - light: `review_light` + `publish_entry`;
  - heavy: `review_heavy` + `publish_entry`.
- Reject uses Phase 5 checks:
  - light: `review_light` + `deprecate_entry`;
  - heavy: `review_heavy` + `deprecate_entry`.
- Role and permissions come only from `RolesConfig.permissions_for_user`.
- Caller-supplied role headers are ignored.

Attack examples:

- `X-KB-User: alice` contributor cannot approve/reject.
- `X-KB-User: reader` cannot load queue.
- `X-KB-Role: admin` does not grant privileges.

### 3. Caller Self-Claims Must Not Control Review

Verify approve/reject body accepts only optional `note` and rejects:

- `reviewer`
- `role`
- `review_level`
- `target_dir`
- `trust_state`
- `operation`
- path fields

Verify the reviewer identity used in audit is the server-derived `X-KB-User`
resolved through `RolesConfig`, not a request body value.

### 4. Phase 5 Release-Gate Semantics Survive HTTP

Verify through tests or direct reading:

- net-new approve still refuses an existing `entries/{id}` unless the staging
  proposal is system-proven update/republish;
- update proposal approve still records `review_republish`;
- `deprecated/{id}` remains terminal and blocks republish;
- per-entry lock still returns `E_DUP`;
- audit append failure rolls back target writes;
- source cleanup failure remains `ok=True` with warning;
- symlink/path/id guards remain Phase 5 owned.

### 5. HTTP Write Attack Surface

Verify:

- `X-KB-User` is required.
- Unknown users fail closed.
- `X-KB-Write-Intent: web-edit` is required for approve/reject.
- `Content-Type: application/json` is required for approve/reject.
- URL traversal in `{id}` is blocked.
- There is no alternate publish shortcut endpoint.

Codex smoke should actively try:

- contributor approve/reject;
- reader queue access;
- role/reviewer spoofing;
- `trust_state=published` injection;
- missing write-intent header;
- form-encoded approve/reject;
- traversal id;
- stale review lock;
- nonexistent shortcut publish endpoint.

### 6. Frontend Boundary

Verify:

- frontend calls HTTP API only;
- queue requires the UI `User` field;
- approve/reject sends `X-KB-User`, `X-KB-Write-Intent`, and JSON;
- approve/reject body contains only `note`;
- no reviewer/role/trust-state fields are exposed in the UI body;
- operation errors/warnings are visible.

## Explicit Scope Decision

Self-review is not blocked in Phase 8b. Current design and Phase 5 semantics are
pure RBAC. Add maker-checker (`reviewer != author`) only as a future explicit
policy once team reviewer capacity supports it.

## Out Of Scope

Do not flag as missing:

- maker-checker self-review ban;
- real login/session/token auth;
- production CSRF system;
- research collection UI;
- research promote UI;
- graph/chat UI;
- collector/P9.

## Output Format

```text
# Phase 8b Review by [Reviewer]
## Special Check 1: P5 Service Bypass
## Special Check 2: Reviewer Permissions
## Special Check 3: Review Self-Claims
## Special Check 4: P5 Release-Gate Semantics
## Special Check 5: HTTP Attack Surface
## Special Check 6: Frontend Boundary
## BLOCKER / MAJOR / MINOR / NIT
## Overall: mergeable / mergeable after fixes / has blockers
```
