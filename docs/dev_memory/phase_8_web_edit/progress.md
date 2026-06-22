# Phase 8 - Web Edit / Progress

> Phase 8 turns the human Web surface from read-only into a write entry point.
> The core rule is: HTTP writes are only a transport wrapper for the Phase 2
> Governed API pipeline, never a second persistence path.

## Key Decisions

- Decision: add only two write endpoints for the P8 MVP.
  - `POST /api/entries` proposes a new entry.
  - `PATCH /api/entries/{id}` proposes an edit to an existing published entry.
  - Research collection UI, review approve/reject UI, graph/chat, collector, and review queue UI stay out of scope.

- Decision: Web writes run the full Phase 2 pipeline.
  - `WebWriteService` builds a `MiddlewareContext` and calls `auth_context -> schema_validate -> evidence_validate -> classify_write_route -> review_route -> persist -> audit_append`.
  - The Web layer does not write markdown files, SQLite, or audit logs directly.
  - This keeps Phase 2 fixes for role trust, system-computed diff, ID allocation, review routing, persist, rollback, and audit in force.

- Decision: P8 V1 uses `X-KB-User` as an intranet trust header, not real authentication.
  - Missing/blank user fails closed at the HTTP dependency.
  - Unknown users and insufficient permissions fail closed through Phase 2 `RolesConfig.permissions_for_user`.
  - Caller-supplied role headers are ignored; role/permissions come only from `roles.yaml`.
  - Code comments now state this is not real auth. Token/session auth is a follow-up before wider exposure.

- Decision: `author_type` is server-derived as `human`.
  - HTTP payloads cannot include `author_type`; strict Pydantic models use `extra="forbid"`.
  - `WebWriteService` sets `auth.author_type=human` and payload `author_type=human`.
  - This follows the P6 fail-closed lesson: trust identity/system context, not caller self-claims.

- Decision: Web requests cannot self-declare governance fields.
  - Create rejects extra fields such as `id`, `trust_state`, `author_type`, `changed_fields`, `target_dir`, and `role`.
  - Patch rejects extra fields such as `id`, `trust_state`, `author_type`, `changed_fields`, `change_scopes`, and `review_level`.
  - Update reads the published entry through the P4 safe reader and lets Phase 2 compute the actual diff.

- Decision: Web writes are forced into review/staging for the MVP.
  - `WebWriteService` supplies system-owned `claimed_change_scopes=["web_edit"]`.
  - This is not caller-provided. It is a conservative Phase 8 routing guard so Web submissions do not auto-publish into `entries/`.
  - Result: create/edit responses report `status=pending`, `target_dir=staging`, and the review level from Phase 2.

- Decision: patching an entry with an existing pending proposal fails with `E_DUP`.
  - Reason: P8 does not build a merge UI for concurrent pending proposals.
  - The conservative behavior avoids overwriting `kb/staging/<id>.md` and makes the conflict visible to the human.

- Decision: write intent is guarded by JSON-only plus a custom header.
  - `X-KB-Write-Intent: web-edit` is required for `POST` and `PATCH`.
  - `Content-Type: application/json` is required.
  - This is a minimal intranet CSRF/simple-request guard, not a substitute for real auth.

- Decision: warning propagation from Phase 2 must be preserved.
  - While adding the "self-declared fact gets downgraded" HTTP test, P8 found that `evidence_validate` correctly downgraded the entry, but `persist` overwrote `validation_warnings` during its second validation pass.
  - Fix: `persist` now accumulates existing validation warnings plus its own warnings.
  - This does not change routing, persistence, audit, or validation errors; it only preserves feedback so the Web UI can show "system downgraded claim_type".

## Implementation

- Backend:
  - Added strict write request DTOs in `web_api/service.py`.
  - Added `WebWriteService` as the thin governed pipeline wrapper.
  - Added FastAPI write dependencies in `web_api/app.py`: `X-KB-User`, `X-KB-Write-Intent: web-edit`, and JSON content type.
  - Generalized stale P7a "Readonly" naming in `web_api` docstrings/title to "Web API".

- Frontend:
  - Added minimal create/edit controls to `web/src/App.tsx`.
  - Added `proposeEntry` / `proposeUpdate` API calls.
  - Added write result rendering for pending/review/error/warning feedback.
  - The UI does not expose raw governance fields and sends only HTTP API requests.

- Tests:
  - Backend HTTP tests cover full pipeline order, staging/audit persist, update-to-staging, auth fail-closed, role spoof, self-declared governance fields, traversal/missing IDs, research evidence, duplicate pending proposals, and claim_type downgrade feedback.
  - Frontend tests cover search, new proposal, edit proposal, and that governance fields are not sent.

## Verification

- `uv run ruff format . --check; uv run ruff check .` -> `58 files already formatted`; `All checks passed!`
- `uv run mypy core tests governed-api mcp index scripts research review web_api` -> `Success: no issues found in 58 source files`
- `uv run pytest tests\web_api tests\governed_api -q --no-cov` -> `62 passed, 1 warning`
- `uv run pytest --cov --cov-report=term-missing -q` -> `194 passed, 1 warning`; total coverage `91.95%`
- `npm.cmd run lint` -> `tsc --noEmit` passed
- `npm.cmd test` -> `4 passed`
- `npm.cmd run build` -> Vite build passed

## TODO / Review Watchpoints

- High-risk review must actively check that HTTP write endpoints are thin P2 pipeline wrappers and do not directly write files/audit/SQLite.
- Codex HTTP write smoke must try role/header spoof, missing write intent, unknown user, reader write, payload governance-field spoofing, direct publish attempts, traversal, research evidence, and nonexistent write/review/research endpoints.
- TODO: replace `X-KB-User` intranet trust header with real authentication before broader rollout.
- TODO: add proper CSRF/token/session model together with real auth.
- TODO: build a merge/replace flow for duplicate pending proposals if humans need to update an already pending edit.

## R14 Closure

Root cause from review: P8 write security was sound, but two older component assumptions broke under the new Web edit flow.

- P1/P2 ID allocation assumed callers rebuild the SQLite sequence before allocating.
- P5 approve assumed `entries/{id}` not existing always meant a net-new publish, but P8 update proposals intentionally target an existing published id.

Fixes:

- FIX-1 BLOCKER: Web create now rebuilds the held `IDAllocator` from `entries/staging/drafts/deprecated` before allocating. `persist()` also has a second guard: if an allocated id already exists in any official ID directory, it returns `E_DUP` before writing.
  - Test: existing `entries/KB-2026-0001.md` plus empty `ids.sqlite` produces Web `proposed_id=KB-2026-0002`, not `0001`.
  - Test: stale allocator in `persist()` fails with `E_DUP` and writes no staging file.

- FIX-2 MAJOR: P5 approve now supports update/republish proposals without weakening net-new publish rules.
  - The authority source is the P2 audit record: only `operation=propose_update` / `update` in the staging audit metadata opens the republish path.
  - Net-new proposals still reject if `entries/{id}` already exists.
  - `deprecated/{id}` remains terminal and still blocks republish.
  - Republish writes `entries/{id}` atomically through `write_entry`, records audit operation `review_republish`, and restores the old published entry if audit append fails.
  - Queue now includes update proposals with an existing published target instead of treating them as stale residue.

- FIX-3 MINOR: Web writes no longer rely only on the magic `web_edit` scope to stay pending. A Web-only invariant runs after `review_route` and before `persist`; if `target_dir != staging`, it fails before any write.

- FIX-4 MINOR: Added explicit `application/x-www-form-urlencoded` test proving write requests return `415` without JSON content type, while missing write intent remains `403`.

P5 regression focus:

- Update approve covers republish overwrite + `review_republish` audit.
- Net-new approve still returns `E_DUP` when target exists.
- Republish still rejects deprecated terminal conflicts.
- Republish audit failure restores the old published entry and keeps staging.
- Existing P5 tests for normal approve/reject, permissions, locks, symlink rejection, audit rollback, source cleanup warning, and id fullmatch continue to pass.

R14 verification:

- `uv run pytest tests\review tests\web_api tests\governed_api -q --no-cov` -> `89 passed, 1 warning`
- `uv run ruff format . --check; uv run ruff check .` -> `58 files already formatted`; `All checks passed!`
- `uv run mypy core tests governed-api mcp index scripts research review web_api` -> `Success: no issues found in 58 source files`
- `uv run pytest --cov --cov-report=term-missing -q` -> `202 passed, 1 warning`; total coverage `92.01%`
- `npm.cmd run lint` -> passed
- `npm.cmd test` -> `4 passed`
- `npm.cmd run build` -> passed

R14 TODO:

- Concurrent PATCH TOCTOU: P8 checks for existing pending proposals before write, but there is no per-entry Web edit lock yet.
- IDAllocator singleton/lifecycle: P8 rebuilds before Web create, but allocator lifetime is still per app/service construction.
- Trust-state placeholder wording: update payload is built from a published entry before `review_route` changes it to pending; add clearer comments if this confuses future maintainers.

## Post-Merge Runtime Finding

- 2026-06-22: real Web edit use found `422 Unprocessable Entity` on entry edit.
  Root cause: the frontend reused the create payload for PATCH and sent
  `entry_type`, while `WebEntryPatchRequest` is strict (`extra=forbid`) and
  intentionally does not accept immutable create-only fields. Fix: split
  frontend payload construction into `createPayload()` (includes `entry_type`)
  and `updatePayload()` (omits `entry_type`), with a regression test asserting
  edit PATCH bodies do not include `entry_type`. This was an integration gap:
  review covered DTO/handler behavior, but not the normal browser edit submit
  path end to end.
