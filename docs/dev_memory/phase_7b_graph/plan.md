# Phase 7b - Knowledge Graph + Related Editing / Plan

## Goal

Phase 7b adds a minimal knowledge graph experience and exposes the existing
`related` entry field in the Web editor. This phase has two different risk
surfaces:

- Related editing is a Web write-path extension. It must continue to use the
  Phase 8 `propose_entry_from_web` / `propose_update_from_web` wrappers and the
  Phase 2 governed pipeline.
- Graph visualization is read-only. It must reuse the Phase 7a/P4 published-only
  read boundary and must not introduce a new path that can read `research/`,
  `staging/`, or `drafts/`.

The core rule is: add relationship ergonomics and visualization without
creating a second write path or a second unguarded directory scanner.

## Baseline

- Branch: `phase/7b-graph`
- Baseline commit: `6a7675e005040b56a29fa25931e813fc87c4adb0`

## Scope

### Part 1: Related Editing (Write Side)

- Extend the React create/edit form with a `related` control.
  - Create and edit should both support related edges.
  - Minimal UX: one edge per line or a compact repeated row editor.
  - Fields: target KB id, edge type, optional note.
  - `origin` is system-owned/human-owned for V1 and must not become an LLM
    self-assertion surface.
- Keep HTTP writes on the existing Phase 8 route:
  - `POST /api/entries`
  - `PATCH /api/entries/{id}`
  - no new related-specific write endpoint in this phase.
- Keep writes in the Phase 2 pipeline:
  - `auth_context`
  - `schema_validate`
  - `evidence_validate`
  - `classify_write_route`
  - `review_route`
  - `_require_web_staging_target`
  - `persist`
  - `audit_append`
- Strengthen related validation.
  - Target id shape: `^KB-\d{4}-\d{4}$`.
  - Self-reference: reject `entry.related[*].target == entry.id`.
  - Existence: target must exist in `entries/`, `staging/`, or `deprecated/`;
    it does not need to be published at write time.
  - Research targets are rejected by shape (`R-*`) and by existence lookup
    never consulting `research/`.
  - Pending/deprecated related targets are accepted as "pre-wired" links, but
    the graph read side only renders the edge once both ends are published.
- Cycle behavior:
  - A -> B and B -> A is allowed; graph cycles are normal knowledge topology.
  - A -> A is rejected as a self-edge.
- Security inheritance:
  - Auth remains P8 `X-KB-User` intranet MVP trust header plus `RolesConfig`.
  - `X-KB-Write-Intent: web-edit` and JSON-only write requests remain required.
  - Strict DTOs continue to reject governance fields such as id, trust_state,
    changed_fields, role, author_type, target_dir, and review_level.
  - Related edits still produce staging proposals and require review; they never
    update `entries/` directly.

### Part 2: Knowledge Graph (Read Side)

- Add a read-only graph HTTP endpoint:
  - `GET /api/graph`
  - optional query params may include `module` and/or a centered `id` if needed
    for MVP ergonomics.
- Graph data source:
  - published entries only, loaded through the same P7a/P4 safe reader used by
    categories/browse: `read_valid_entries_from_source(kb_root, "entries")`.
  - no scanning `research/`, `staging/`, `drafts/`, or `deprecated/`.
  - no direct SQLite-specific shortcut unless it preserves the same source-root
    whitelist and validation behavior.
- Graph response shape:
  - nodes: id, title, module, entry_type, trust_state, claim_type,
    support_strength, stale flag.
  - edges: source id, target id, types, origins, notes, bidirectional flag.
  - edges pointing to unpublished/missing nodes are omitted. This keeps the
    graph as the current published view while allowing pending links to appear
    automatically after review approval.
- Frontend:
  - minimal graph panel in the existing React shell.
  - use a small dependency only if needed; design allows D3.js / ECharts and
    explicitly says no Neo4j.
  - preferred MVP: SVG/React force-light or D3 force graph with clickable nodes.
  - click node opens/loads existing entry detail through `GET /api/entries/{id}`.
  - no complex filtering, graph search, clustering, graph editing, or layout
    persistence in this phase.
- Isolation tests:
  - research-only node/tag/edge must not appear in graph data.
  - staging/pending related edges must not appear in graph data.
  - traversal/bad id params are rejected if a centered graph endpoint is added.

## Explicit Non-Goals

- No Chat UI or `/api/search/nl` in this phase, despite the older design line
  that grouped Chat with P7b.
- No research collection UI.
- No P9 collector.
- No graph auto-linking, rule-suggested edges, or LLM-suggested edges.
- No Neo4j or separate graph database.
- No review workflow changes.
- No changes to P1-P8 core governance semantics except adding related validation
  needed to protect the existing `related` field.

## File Plan

- `core/validation.py`
  - Add related target shape/self-edge/existence validation.
  - Keep validation path-aware and fail closed when existence checks need
    `kb_root`.
- `core/models.py`
  - Prefer no schema churn; `RelatedEdge` already exists.
  - Only adjust if V1 needs default `origin=human` or stricter field semantics.
- `web_api/service.py`
  - Add graph DTO construction in the read service.
  - Reuse published-only safe entry loading.
  - Preserve Web write wrappers for related payloads.
- `web_api/app.py`
  - Add `GET /api/graph`.
  - No related-specific write route.
- `web/src/types.ts`
  - Add typed `RelatedEdge`, graph node/edge/response, and related in
    `EntryWritePayload`.
- `web/src/api.ts`
  - Add `getGraph()` and include related in create/edit payloads.
- `web/src/App.tsx`
  - Add related editor control.
  - Add minimal graph panel and node-click detail flow.
- `web/src/styles.css`
  - Add graph and related editor styles with stable dimensions.
- `tests/core/test_validation.py`
  - Add related id shape, self-edge, missing target, and valid target tests.
- `tests/web_api/test_app.py`
  - Add graph endpoint tests for published-only isolation and related payload
    persistence through P8 write wrappers.
- `web/src/App.test.tsx`
  - Add frontend tests for related submission and graph loading/click behavior.
- `docs/dev_memory/phase_7b_graph/progress.md`
  - Record implementation decisions and any scope/risk changes.
- `docs/review/phase_7b_review_prompt.md`
  - Add review prompt with write-side related and read-side graph isolation
    special checks.

## DoD

- Related create/edit works through existing Web propose endpoints and lands in
  `staging/` pending review.
- Related target validation rejects malformed ids, self-edges, and missing or
  never-issued targets.
- Related write tests prove P8 auth/CSRF/governance-field boundaries still hold.
- `GET /api/graph` returns nodes and typed edges for published entries only.
- Graph endpoint tests prove `research/`, `staging/`, `drafts/`, and traversal
  cannot leak into graph data.
- React graph UI renders nodes/edges and clicking a node loads detail.
- React related editor sends `related` without sending governance fields.
- Python gates pass:
  - `uv run ruff format . --check`
  - `uv run ruff check .`
  - `uv run mypy core tests governed-api mcp index scripts research review web_api`
  - `uv run pytest --cov --cov-report=term-missing -q`
- Frontend gates pass:
  - `npm.cmd run lint`
  - `npm.cmd test`
  - `npm.cmd run build`

## Review Focus

- Related edit must not open a new write path.
- Related validation must not allow malformed ids, self-reference, or hidden
  research/staging targets.
- Graph endpoint must not open a new unguarded scan path.
- Graph data must not include research, staging, draft, deprecated, or hidden
  dangling target content.
- Frontend must not send caller-owned governance fields.
- Large graph performance is not optimized in MVP, but the endpoint should have
  a conservative response shape and predictable source set.
