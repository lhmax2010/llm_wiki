# Phase 8b - Web Review UI / Plan

## Baseline

- Branch: `phase/8b-web-review`
- Baseline commit: `ecdd984c1635453a62d42f083c393b0abd0149a1`
- Parent context:
  - Phase 5 provides the staging review service.
  - Phase 8 provides the Web write auth/intent/header pattern.
  - Phase 8 explicitly left review approve/reject UI out of scope.

## Risk Class

- Verdict: high risk.
- Reason: this phase adds another HTTP write surface, and the operation is more
  privileged than propose/edit. `approve` publishes into `entries/`; `reject`
  moves content to `deprecated/`. A Web bug here can bypass or weaken the Phase 5
  release gate.
- Required review strength: Claude + ChatGPT + Kimi, plus Codex HTTP write
  attack-surface smoke, matching Phase 8.

## Goal

Expose Phase 5 review queue and review decisions through the Web app without
reimplementing review state transitions.

The core rule: the Web API is only an HTTP wrapper around `review.service`.
It must not implement its own publish, deprecate, republish, audit, lock, or file
movement logic.

## Scope

### HTTP Review Endpoints

- Add authenticated review endpoints:
  - `GET /api/review/queue`
  - `POST /api/review/{entry_id}/approve`
  - `POST /api/review/{entry_id}/reject`
- `GET /api/review/queue` maps to `list_review_queue`.
- `POST approve` maps to `approve_staging_entry`.
- `POST reject` maps to `reject_staging_entry`.
- Approve/reject request body should be strict and minimal:
  - optional `note`;
  - no `reviewer`, `role`, `review_level`, `target_dir`, `trust_state`,
    `operation`, or path fields from callers.

### Phase 5 Reuse Invariants

- The HTTP layer must call Phase 5 service functions directly.
- The HTTP layer must not:
  - write to `kb/entries`, `kb/staging`, `kb/deprecated`, `kb/indexes`, or audit;
  - set `trust_state`;
  - decide republish/net-new behavior;
  - inspect or override terminal-state rules;
  - manage review locks itself.
- Phase 5 remains the owner of:
  - terminal mutual exclusion across `entries/` and `deprecated/`;
  - per-entry `O_CREAT|O_EXCL` review lock;
  - update proposal republish mode;
  - audit append and audit-failure rollback;
  - source cleanup warning semantics;
  - path/id/symlink guards.

### Auth And Permissions

- Reuse Phase 8's V1 intranet trust model:
  - `X-KB-User` is required.
  - The header is not real authentication; unknown users fail closed through
    `RolesConfig`.
  - Role and permissions come only from `RolesConfig.permissions_for_user`.
- Reuse Phase 8's write guard for mutating endpoints:
  - `X-KB-Write-Intent: web-edit` required for approve/reject.
  - `Content-Type: application/json` required for approve/reject.
- Queue access is not public:
  - require a reviewer-capable user before returning pending staging metadata;
  - planned permission check: admin or at least one of `review_light` /
    `review_heavy`.
- Approve must rely on Phase 5's permission checks:
  - light entries require `review_light` + `publish_entry`;
  - heavy entries require `review_heavy` + `publish_entry`.
- Reject must rely on Phase 5's permission checks:
  - light entries require `review_light` + `deprecate_entry`;
  - heavy entries require `review_heavy` + `deprecate_entry`.
- Contributors/readers must not approve or reject.

### Frontend

- Extend the existing React shell with a minimal reviewer work surface:
  - review queue panel/list;
  - per-item metadata: id, title, module, entry type, claim type,
    support strength, review level, updated, path;
  - select item to view details through existing `get_entry` if published
    update target exists, or via a review-specific safe pending detail endpoint
    only if needed and explicitly covered by the plan during restate;
  - approve/reject buttons;
  - optional note input;
  - operation result/warning/error feedback.
- Frontend calls only the HTTP API. It never reads local files.

## Security And Attack-Surface Tests

- HTTP route tests:
  - queue requires known reviewer-capable user;
  - unknown user fails closed;
  - contributor cannot approve;
  - contributor cannot reject;
  - reader cannot see queue;
  - missing write intent fails approve/reject;
  - form-encoded approve/reject returns 415;
  - invalid/traversal id fails before any write;
  - caller-supplied governance fields are rejected.
- Phase 5 boundary tests through HTTP:
  - approve net-new publishes by calling P5 service;
  - approve update proposal republish uses existing P5 behavior;
  - net-new duplicate target still fails `E_DUP`;
  - deprecated terminal conflict still fails;
  - audit failure rolls back through P5 service;
  - stale lock / concurrent transition behavior remains P5-owned.
- Codex smoke:
  - try approving as contributor;
  - try spoofing role/reviewer in JSON;
  - try direct `trust_state=published`;
  - try missing/unknown `X-KB-User`;
  - try missing write-intent header;
  - try URL traversal in review id;
  - verify no alternative publish endpoint exists.

## Design Point To Confirm

- Self-review:
  - `docs/design.md` and the current Phase 5 service do not appear to require
    `submitter != reviewer`.
  - Default plan: do not add a new self-review prohibition in Phase 8b; enforce
    only role/permission gates through `RolesConfig`.
  - If a maker-checker rule is desired, it should be explicitly confirmed and
    added as a new policy with tests, because it changes existing Phase 5
    semantics.

## Out Of Scope

- Research collection UI.
- Research promote UI.
- P7b graph/chat.
- P9 collector and batch preview.
- Real login/session/token authentication.
- RBAC management UI or dynamic workflow editor.
- Rewriting Phase 2 or Phase 5 core logic.

## File Plan

- Backend:
  - `web_api/app.py`: add review routes and reuse existing auth/write guards.
  - `web_api/service.py`: add a thin `WebReviewService` facade that delegates to
    `review.service`; keep DTOs strict.
  - `tests/web_api/test_app.py`: add HTTP review tests and attack-surface cases.
- Frontend:
  - `web/src/api.ts`: add review queue/approve/reject client calls.
  - `web/src/types.ts`: add review queue/result types.
  - `web/src/App.tsx`: add minimal review panel/actions.
  - `web/src/App.test.tsx`: cover reviewer UI calls and error feedback.
- Docs/review:
  - `docs/dev_memory/phase_8b_web_review/progress.md`
  - `docs/dev_memory/phase_8b_web_review/result.md`
  - `docs/review/phase_8b_review_prompt.md`

## DoD

- Review queue and approve/reject are usable from the Web UI.
- HTTP review endpoints are thin wrappers around Phase 5 service.
- No Web review endpoint writes files, audit logs, or SQLite directly.
- Contributors/readers cannot approve/reject; unknown users fail closed.
- Queue is not anonymous and does not expose staging metadata to non-reviewers.
- Approve/reject preserve Phase 5 terminal mutual exclusion, per-entry lock,
  republish, audit rollback, symlink/path/id guards, and source cleanup warning
  behavior.
- Python R13 gates pass with real output:
  - ruff format/check;
  - mypy;
  - pytest with coverage.
- Frontend gates pass with real output:
  - lint/typecheck;
  - tests;
  - build.
- Review prompt contains special checks for:
  - HTTP privilege escalation;
  - P5 service bypass;
  - republish/terminal-state regression;
  - reviewer identity spoofing;
  - CSRF/content-type guard.
