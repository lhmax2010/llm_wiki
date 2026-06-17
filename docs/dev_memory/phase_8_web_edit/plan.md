# Phase 8 - Web Edit / Plan

## 目标

Phase 8 adds the first human-facing Web write surface. P7a made the Web app useful for read-only search/detail; P8 must let humans propose new entries and submit edits through HTTP and React without creating any write path that bypasses the Phase 2 Governed API pipeline.

The core rule for this phase is: Web write endpoints are HTTP wrappers around existing governance, not a second implementation of persistence, validation, routing, review, or audit.

## 范围边界

### HTTP write surface

- Add minimal write endpoints for human entry contribution:
  - `POST /api/entries` for propose/create.
  - `PATCH /api/entries/{id}` or equivalent submit-edit endpoint for propose/update.
- Each endpoint maps to the existing Governed API operation and must run the full P2 chain:
  - `auth_context`
  - `schema_validate`
  - `evidence_validate`
  - `classify_write_route`
  - `review_route`
  - `persist`
  - `audit_append`
- No HTTP endpoint may write directly to `kb/entries/`, `kb/staging/`, `kb/drafts/`, `kb/research/`, audit logs, or SQLite.
- No endpoint may trust caller-declared role, changed fields, review level, id, trust state, or author type.

### Authentication and authorization

- P7a was anonymous read-only. P8 writes require an explicit authenticated user context, even if V1 keeps it intranet-simple.
- V1 auth candidate to confirm before coding:
  - Use a small server-side header/user context for local intranet testing.
  - Resolve role and permissions through Phase 2 `RolesConfig.permissions_for_user`.
  - `author_type` is system-derived as `human` for Web writes, not accepted from request payload.
- Required write permission comes from P2 RBAC, especially `propose_entry`.
- Admin/reviewer/contributor role expansion remains YAML-driven; no Web-specific policy engine.

### Governance invariants

- Entry create/update must use Phase 2 pipeline and Phase 1 validation.
- Evidence validation must be inherited from `core.validation.validate_entry()` through P2 `evidence_validate`.
- Create/propose must reject payload-supplied `id`; ID allocation remains Phase 1/P2 responsibility.
- Update/propose must use system-computed diff behavior from P2, not caller-supplied `changed_fields` / `change_scopes`.
- Writes route to staging/review according to P2/P5 discipline. Web cannot directly publish content into `entries/`.
- Research evidence remains forbidden through P6/P1 validation.

### React frontend

- Extend the P7a React UI with a minimal edit contribution surface:
  - new entry form;
  - edit existing entry flow from detail view;
  - visible validation/warning/review result feedback;
  - no raw internal file writes.
- Keep UI operational and restrained. This is a work surface, not a marketing page.
- Frontend calls HTTP API only; it never reads/writes local files.

### Design-scope watchpoint

Design §7 says Phase 8 includes "人编辑（分级）+ research 收集 UI" and mentions review operation UI. This plan treats entry propose/edit as the core P8 write surface. After risk confirmation, the restate must explicitly pin whether this implementation also includes:

- research create/promote UI;
- review approve/reject UI;
- or only enough review visibility to show "pending/light/heavy" result.

This is a deliberate scope gate because every additional Web write/review surface is another HTTP trust boundary.

## 明确不做

- Do not implement P7b graph or chat UI.
- Do not implement P9 collector or batch preview.
- Do not rewrite P1-P6 core validation, pipeline, review, search, or research isolation.
- Do not build a complex login/session system unless explicitly confirmed; V1 auth should be a narrow server-side context that feeds P2 RBAC.
- Do not build a dynamic RBAC policy engine, RBAC management UI, workflow editor, or visual rule editor.
- Do not add direct publish/approve shortcuts that skip staging/review.

## 计划步骤

1. Inspect current P7a FastAPI service/app boundaries and P2 pipeline API.
2. Define Web write request/response DTOs that exclude untrusted fields (`role`, `author_type`, `id` on create, `changed_fields`, `trust_state`).
3. Add HTTP write handlers that construct P2 `MiddlewareContext` and call the existing pipeline.
4. Add V1 auth extraction that resolves user/role/permissions through `RolesConfig`; unknown users and missing permissions fail closed.
5. Add tests for create/update success paths, validation errors, evidence errors, staging/review routing, audit behavior, and trust-boundary attacks.
6. Extend React UI with minimal create/edit forms and result handling.
7. Add frontend tests for form submission, validation errors, and "write goes through HTTP API" behavior.
8. Add review prompt with special HTTP write bypass checks.
9. Run R13 gates: ruff format/check, mypy, pytest coverage, frontend lint/test/build, plus HTTP write attack-surface smoke.

## 依赖

- P1: content schema, validation, ID allocation, safe storage.
- P2: Governed API pipeline, RBAC, audit, trust-boundary fixes.
- P5: staging/review lifecycle and review semantics.
- P6: research isolation and research evidence rejection.
- P7a: FastAPI read-only app, React/Vite shell, Web runtime notes.

## DoD

- HTTP write endpoints exist only for confirmed P8 scope and are covered by tests.
- Every Web write goes through the complete P2 governed pipeline.
- Caller cannot self-declare role, author_type, id, trust_state, changed_fields, review_level, or publish destination.
- Web create/update cannot directly write `entries/` or bypass review/staging.
- RBAC is enforced through `RolesConfig`; unknown users fail closed.
- Evidence validation, research evidence rejection, ID allocation, diff classification, persist, and audit are inherited from existing core/governed modules.
- React create/edit workflow is minimally usable and surfaces validation warnings/errors/review status.
- HTTP attack tests cover write endpoint absence/presence, invalid id/traversal, role spoofing, id spoofing, changed_fields spoofing, direct publish attempts, research evidence, and missing/unknown auth.
- Python and frontend gates pass with real command output.

## Baseline

- Branch: `phase/8-web-edit`
- Baseline commit: `61155dbfa7ea35e7e1278da51d956045b3c6afa2`
