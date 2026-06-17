# Phase 8 Review Prompt - Web Edit

## How To Review

Code is on branch `phase/8-web-edit`. Focus on:

- `web_api/app.py`
- `web_api/service.py`
- `governed-api/governed_api/middleware.py`
- `tests/web_api/test_app.py`
- `web/src/App.tsx`
- `web/src/api.ts`
- `web/src/App.test.tsx`

Design baseline: `docs/design.md` v1.4, especially Phase 8, Phase 2 governed pipeline, Phase 5 review flow, and Phase 6 research evidence isolation.

## Background

Phase 8 is the first human Web write surface. P7a was read-only; P8 adds a minimal edit/submit path:

- human create entry -> propose through Phase 2 -> staging/pending;
- human edit published entry -> propose update through Phase 2 -> staging/pending.

This phase deliberately does not implement research collection UI, review approve/reject UI, graph/chat, or collector.

The head risk: HTTP writes must not become a second write path. Web API must be a thin transport wrapper around the existing Phase 2 governed pipeline.

## Special Checks

### 1. HTTP Writes Must Not Bypass Phase 2

Verify:

- `POST /api/entries` and `PATCH /api/entries/{id}` call `WebWriteService`.
- `WebWriteService` calls `run_pipeline()` with the full seven-step pipeline:
  `auth_context`, `schema_validate`, `evidence_validate`, `classify_write_route`, `review_route`, `persist`, `audit_append`.
- Web code does not directly write `kb/entries/`, `kb/staging/`, `kb/drafts/`, `kb/research/`, audit logs, or SQLite.
- Web writes end in `staging/` for P8 MVP and do not directly publish into `entries/`.

### 2. Identity / Role Trust Boundary

Verify:

- `X-KB-User` is treated only as an intranet MVP trust header, not real authentication.
- Missing/blank `X-KB-User` fails closed.
- Unknown users fail closed through `RolesConfig.permissions_for_user`.
- Caller-supplied role headers are ignored.
- Payload-supplied `author_type` is rejected; server derives `author_type=human`.

Attack examples:

- `X-KB-User: reader`, `X-KB-Role: admin` must still fail write permission.
- Missing user or unknown user must fail.

### 3. Caller Self-Claims Must Not Control Governance

Verify create rejects self-declared:

- `id`
- `trust_state`
- `author_type`
- `changed_fields`
- `target_dir`
- `role`

Verify patch rejects self-declared:

- `id`
- `trust_state`
- `author_type`
- `changed_fields`
- `change_scopes`
- `review_level`

Verify:

- patch reads the existing published entry and lets Phase 2 compute the actual diff;
- pending duplicate proposals for the same id return `E_DUP`;
- self-declared `claim_type=fact` is system-downgraded or rejected according to evidence, not accepted as truth.

### 4. HTTP Write Attack Surface

Verify:

- `X-KB-Write-Intent: web-edit` is required.
- `Content-Type: application/json` is required.
- URL traversal through `PATCH /api/entries/{id}` is blocked by KB id validation.
- Direct publish attempts cannot set target `entries/`.
- Research evidence is rejected with `E_RESEARCH_AS_EVIDENCE`.
- No write/review/research endpoints exist outside the two intended P8 routes.

Codex smoke should actively try:

- role spoof;
- missing CSRF/write-intent header;
- unknown user;
- reader write;
- payload id/trust_state/changed_fields/review_level spoof;
- traversal id;
- research evidence URI;
- nonexistent approve/research endpoints.

### 5. Frontend Boundary

Verify:

- frontend calls HTTP API only;
- create/edit form does not expose raw governance fields;
- frontend sends `X-KB-User` and `X-KB-Write-Intent`;
- frontend surfaces validation errors, warnings, pending status, and review level.

## Out Of Scope

Do not flag as missing:

- real login/session/token auth;
- production CSRF system;
- research collection UI;
- review approve/reject UI;
- graph/chat UI;
- collector/P9.

Real auth and stronger CSRF are known TODOs before broader rollout.

## Output Format

```text
# Phase 8 Review by [Reviewer]
## Special Check 1: P2 Pipeline Bypass
## Special Check 2: Identity / Role Boundary
## Special Check 3: Caller Self-Claims
## Special Check 4: HTTP Write Attack Surface
## Special Check 5: Frontend Boundary
## BLOCKER / MAJOR / MINOR / NIT
## Overall: mergeable / mergeable after fixes / has blockers
```
