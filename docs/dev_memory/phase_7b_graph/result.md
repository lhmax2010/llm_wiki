# Phase 7b - Knowledge Graph + Related Editing / Result

## Current Status

Implemented on branch `phase/7b-graph`; ready for three-way review plus Codex
HTTP/graph smoke.

Phase 7b adds related editing to the existing Web create/edit flow and adds a
published-only graph view. The write side remains a thin extension of P8 Web
propose routes, and the read side remains a P7a/P4 published-entry view.

## Delivered

- Related editing:
  - React create/edit form accepts related lines.
  - Payload goes through existing `POST /api/entries` and
    `PATCH /api/entries/{id}`.
  - No related-specific write endpoint was added.
  - P1 `validate_entry()` validates related targets for all write/read entry
    validation paths.
- Related validation:
  - only `KB-\d{4}-\d{4}` targets are accepted;
  - research ids are rejected by shape and existence lookup never checks
    `research/`;
  - target must exist in `entries/`, `staging/`, or `deprecated/`;
  - self-related is rejected;
  - cycles are allowed.
- Graph API:
  - `GET /api/graph`;
  - nodes are published entries only;
  - edges are rendered only when both ends are published;
  - reciprocal A<->B edges collapse into one visual edge with
    `bidirectional: true`.
- Frontend graph:
  - lightweight React/SVG graph, no new npm dependency;
  - graph button loads `/api/graph`;
  - clicking a node loads the normal entry detail through `GET
    /api/entries/{id}`.
- Review prompt:
  - `docs/review/phase_7b_review_prompt.md`.

## Verification

- Targeted:
  - `uv run pytest tests\core\test_validation.py -q --no-cov` -> `43 passed`
  - `uv run pytest tests\web_api\test_app.py -q --no-cov` ->
    `38 passed, 1 warning`
  - `npm.cmd test -- --run` -> `7 passed`
- Python static checks:
  - `uv run ruff format . --check` -> `58 files already formatted`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts research review web_api` ->
    `Success: no issues found in 58 source files`
- Python tests:
  - `uv run pytest --cov --cov-report=term-missing -q` ->
    `218 passed, 1 warning`
  - Total coverage: `92.32%`
- Frontend:
  - `npm.cmd run lint` -> passed
  - `npm.cmd test` -> `7 passed`
  - `npm.cmd run build` -> passed

## Runtime Notes

- Start backend from repo root:
  - `uv run uvicorn web_api.app:app --host 127.0.0.1 --port 8000`
- Start frontend:
  - `cd web`
  - `npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`
- Visit:
  - `http://127.0.0.1:5174`
- Restart both backend and frontend after pulling this branch. The backend needs
  the new `/api/graph` route and the frontend needs the new Graph button and
  related editor.

## Remaining Risks / TODO

- Large graph performance is not optimized in MVP. Add caching, centering, or
  filtering if graph size grows.
- Related duplicate-edge normalization is not enforced at storage time. The
  graph response collapses reciprocal visual edges, but repeated stored human
  edges can still exist.
- `X-KB-User` remains the P8 intranet MVP trust header. Real authentication is
  still required before broader exposure.
