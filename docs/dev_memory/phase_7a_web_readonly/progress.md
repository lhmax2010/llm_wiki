# Phase 7a - Web Readonly / Progress

> P7a is the first network-reachable surface. The core rule is: HTTP reads must
> reuse existing P3/P4/P6 isolation, not open a new KB directory reader.

## 关键决策

- Decision: use FastAPI for the read-only HTTP API.
  - Reason: design fixes Python backend but does not choose FastAPI/Flask. FastAPI fits the existing Pydantic boundary, gives typed query validation, and has a direct test client for HTTP attack-surface tests.
  - Dependency install: added `fastapi`, `uvicorn[standard]`, and dev `httpx`; `uv sync --system-certs` installed successfully and import check reported `fastapi=0.137.1`, `uvicorn=0.49.0`, `httpx=0.28.1`.

- Decision: HTTP API registers only `GET` routes.
  - Implemented routes: `GET /api/entries`, `GET /api/entries/{id}`, `GET /api/categories`, `GET /api/browse`.
  - Excluded routes: no propose/update/review/research/collector/draft/write endpoints, and no `POST`/`PUT`/`PATCH`/`DELETE`.
  - Reason: P7a is read-only. Web write/review/research UI belongs to later phases.

- Decision: `/api/entries` uses `SearchService.search_human()` first, then an entries-only P4 fallback.
  - Reason: P4 already built `human_search_index`; P7a should consume it rather than reimplement search.
  - Implementation: added `SearchService.search_human_direct()` that reuses P4 `read_valid_entries_from_source("entries")` for fallback. It does not scan `staging/`, `drafts/`, or `research/`.

- Decision: `GET /api/entries/{id}` has its own thin guard, then delegates parsing/validation to P4.
  - Guard: fullmatch `^KB-\d{4}-\d{4}$`, published `entries/` only, resolve + `is_relative_to`.
  - Delegation: `read_valid_entry_file(kb_root, "entries", ...)` so bad markdown/trust_state/path issues are handled by the P4 safe reader.
  - Reason: URL path params are a new traversal surface; shape validation must happen before file path use.

- Decision: `categories` and `browse` also use the published-only P4 reader.
  - Reason: aggregation endpoints can leak research via tags/error_codes/modules if they scan the wrong directories. P7a treats them as security-sensitive read paths, not harmless summaries.
  - Implementation: both call `read_valid_entries_from_source(kb_root, "entries")`; tests prove staging/research tags do not appear.

- Decision: frontend is a minimal Vite/React workbench.
  - Scope: search box, results list, detail panel.
  - Data access: fetches only HTTP API; no direct filesystem reads.
  - Human view: backend returns complete JSON, while frontend renders a human-readable subset and does not dump frontmatter/internal fields such as `schema_version` or `author_type`.

- Decision: npm requires explicit local machine proxy/cert handling.
  - Observed: `npm install` and `npm view react version` hung while Node tried direct registry connections; PowerShell `Invoke-WebRequest` could reach registry through the corporate proxy.
  - Fix: set npm user-level `proxy` and `https-proxy` to the existing corporate proxy, then run npm commands with `NODE_OPTIONS=--use-system-ca`.
  - Result: `npm install` completed; production audit with `npm audit --omit=dev` reported `0 vulnerabilities`. npm still reports dev-toolchain high vulnerabilities in full audit, not production dependencies.

## 已完成

- Added `web_api/` FastAPI app and read-only service.
- Added `tests/web_api/` with HTTP attack-surface coverage:
  - research not searchable through HTTP;
  - index-unavailable fallback still entries-only;
  - invalid/traversal IDs rejected or not found;
  - staging/research not readable via `get_entry`;
  - categories/browse do not leak staging/research tags;
  - write routes are absent;
  - query params are typed/validated.
- Added Vite/React minimal frontend under `web/`.
- Added frontend tests for search/detail rendering and hidden technical fields.

## 当前验证

- `uv run pytest tests\web_api tests\index -q --no-cov` -> `19 passed, 1 warning`
- `uv run mypy core tests governed-api mcp index scripts research review web_api` -> `Success: no issues found in 58 source files`
- `uv run ruff format .` -> `58 files left unchanged`
- `uv run ruff check .` -> `All checks passed!`
- `uv run pytest --cov --cov-report=term-missing -q` -> `181 passed, 1 warning`; total coverage `91.61%`
- `npm run lint` -> `tsc --noEmit` passed
- `npm test` -> `2 passed`
- `npm run build` -> Vite build passed
- Local Web smoke:
  - frontend `http://127.0.0.1:5173` -> `200`, root element present
  - `GET /api/categories` -> `modules=photo`, no pending/research aggregation observed
  - `GET /api/entries?q=8k` -> `KB-2026-0001`
  - `POST /api/entries` -> `405`
  - `GET /api/entries/KB-2026-1` -> `400`
  - encoded traversal `/api/entries/%2E%2E%2Fresearch%2FKB-2026-0001` -> `404`
  - `GET /api/entries?status=research` -> `422`
  - `POST /api/research` -> `404`

## TODO / Review Watchpoints

- Codex review must actively test HTTP-specific bypasses: research search, URL traversal to staging/research, absent write routes, bad query params.
- Dev dependency audit reports high vulnerabilities; production audit is clean. Review whether to pin/upgrade dev tooling after P7a if the audit remains actionable without breaking Vite/Vitest.
- FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass. Track upstream FastAPI/Starlette guidance before upgrading test transport.
