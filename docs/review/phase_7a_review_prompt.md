# Phase 7a Review Request - Web Readonly HTTP + React

## How To Review

Code is on branch `phase/7a-web-readonly`.

Focus files:
- `web_api/app.py`
- `web_api/service.py`
- `index/search.py`
- `tests/web_api/test_app.py`
- `web/src/App.tsx`
- `web/src/api.ts`
- `web/src/App.test.tsx`

Design baseline: `docs/design.md` v1.4, especially §4.1.2 HTTP API and §7 Phase 7a.

## Background

Phase 7a adds the first network-reachable surface for the unified KB: a read-only
FastAPI HTTP API and a minimal React frontend. This phase must not introduce any
write path or bypass P1-P6 isolation. It consumes P4 `human_search_index` and
P4/P6 safe readers.

Out of scope:
- Web editing / P8
- graph or Chat UI / P7b
- research UI
- review UI
- collector

## Special Review Checks

### 1. HTTP Surface Is Strictly Read-Only

Check:
- Only `GET /api/entries`, `GET /api/entries/{id}`, `GET /api/categories`,
  and `GET /api/browse` are registered.
- No `POST` / `PUT` / `PATCH` / `DELETE` write routes exist.
- No propose/update/review/research/collector/draft endpoint leaked into P7a.

Codex empirical checks should include:
- `POST /api/entries`
- `PUT /api/entries/KB-2026-0001`
- `POST /api/research`
- `POST /api/review/KB-2026-0001/approve`

### 2. Research Is Physically Invisible

Check:
- HTTP search uses `SearchService.search_human()` / `human_search_index`.
- `human_search_index` source remains `entries/` only.
- fallback uses `SearchService.search_human_direct()` and only scans `entries/`.
- `categories` and `browse` do not aggregate `research/` tags/modules/error_codes.

Codex empirical checks should place a unique token in `kb/research/` and verify:
- `/api/entries?q=<token>` returns no results.
- `/api/categories` does not include research-only tags/error_codes.
- `/api/browse` does not include research entries.

### 3. URL ID / Path Traversal Is Blocked

Check:
- `GET /api/entries/{id}` validates `^KB-\d{4}-\d{4}$` before path use.
- published read path is `entries/` only.
- final path is resolved and checked with `is_relative_to`.
- staging/research cannot be read through encoded traversal or a valid-looking id.

Codex empirical checks:
- `/api/entries/../research/KB-2026-0001`
- `/api/entries/%2E%2E%2Fresearch%2FKB-2026-0001`
- `/api/entries/KB-2026-0002` where the file exists only in staging/research.

### 4. Query Parameters Are Typed And Bounded

Check:
- `status` only accepts `published`.
- `min_support`, `claim_type`, `entry_type`, `sort`, `limit`, and `offset` are typed/bounded.
- No SQL or filesystem path is constructed from query params.

### 5. Frontend Does Not Bypass HTTP API

Check:
- React uses `fetch("/api/...")`.
- It does not read files directly.
- Human detail view does not dump raw frontmatter/internal fields such as
  `schema_version` or `author_type`.

## Output Format

```
# Phase 7a Review by [Reviewer]
## Special 1: Read-only HTTP surface
## Special 2: Research physically invisible
## Special 3: URL/path traversal
## Special 4: Query validation
## Special 5: Frontend boundary
## BLOCKER / MAJOR / MINOR / NIT
## Overall: mergeable / mergeable after fixes / has blockers
```
