# Phase 7a - Web Readonly / Result

## 最终状态

待 Merge。Phase 7a read-only HTTP API + React minimal frontend 已完成三路 review（Claude + ChatGPT + Codex HTTP 实测），零 BLOCKER / MAJOR；R14 的 2 个 MINOR 已闭环。Python/Frontend gates、ResourceWarning gate 与本机 Web smoke 均已通过，PR #8 可合并。

## 交付内容

- FastAPI read-only HTTP API:
  - `GET /api/entries`
  - `GET /api/entries/{id}`
  - `GET /api/categories`
  - `GET /api/browse`
- React/Vite minimal Web UI:
  - search box;
  - result list;
  - entry detail panel;
  - frontend hides internal/frontmatter-style fields instead of dumping raw JSON.

## 测试情况

- Python:
  - `uv run ruff format .` -> `58 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts research review web_api` -> `Success: no issues found in 58 source files`
  - `uv run pytest --cov --cov-report=term-missing -q` -> `183 passed, 1 warning`
  - Total coverage: `91.68%`
  - ResourceWarning gate: `$env:PYTHONWARNINGS='error::ResourceWarning'; uv run pytest tests\index -q --no-cov` -> `13 passed`
  - touched files:
    - `web_api/app.py`: `95%`
    - `web_api/service.py`: `97%`
    - `index/search.py`: `87%`
- Frontend:
  - `npm run lint` -> passed
  - `npm test` -> `2 passed`
  - `npm run build` -> passed
- Integration smoke:
  - `http://127.0.0.1:5173` -> `200`
  - `GET /api/entries?q=8k` -> `KB-2026-0001`
  - `POST /api/entries` -> `405`
  - `GET /api/entries/KB-2026-1` -> `400`
  - encoded traversal to research -> `404`
  - `GET /api/entries?status=research` -> `422`
  - `POST /api/research` -> `404`

## 运行 / 验收说明

- Start backend from repo root:
  - `uv run uvicorn web_api.app:app --host 127.0.0.1 --port 8000`
- Start frontend:
  - `cd web`
  - `npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`
- Visit:
  - `http://127.0.0.1:5174`
- Frontend and backend must run at the same time. The frontend calls `/api/*`,
  and Vite proxies those requests to backend port `8000`.
- After changing `web/vite.config.ts` proxy settings, restart the Vite dev
  server. The dev server does not reliably hot-reload proxy config; a stale
  process can return `index.html` for `/api/*`, causing frontend JSON parsing to
  fail with `Unexpected token '<'`.
- `web/.vite/` is Vite local cache and must not be committed.

## PR 与代码

- PR link: https://github.com/lhmax2010/llm_wiki/pull/8
- Commits:
  - `969e571` - `[Phase 7a] web readonly HTTP API + React`
  - `f06704d` - `[Phase 7a] fix: R14 minor HTTP error hygiene`
- Review prompt: `docs/review/phase_7a_review_prompt.md`

## Review 状态

- Claude review: 已完成，无 BLOCKER / MAJOR。
- ChatGPT review: 已完成，无 BLOCKER / MAJOR。
- Codex HTTP attack-surface smoke: 已完成，research/staging traversal、write endpoint leakage、invalid id / parameter validation 均未绕过。
- R14 MINOR:
  - FIX-1: HTTP 错误对外返回通用文案，具体异常只记日志；测试覆盖响应不泄漏本地路径。
  - FIX-2: human index SQLite connection audit confirmed existing `closing()` coverage; ResourceWarning gate 通过，无需无效改动。

## 遗留问题 / 风险

- Full npm audit reports dev-toolchain high vulnerabilities; `npm audit --omit=dev` reports `0 vulnerabilities`.
- FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass.
- m1 TODO: network read endpoints currently rebuild/read broadly per request and have no rate limit/cache; acceptable for intranet MVP, tracked in `docs/dev_memory/BACKLOG.md`.
- n1 TODO: `get_entry` currently returns complete internal JSON fields such as `author` / `git_sha`; human-view redaction policy is tracked in `docs/dev_memory/BACKLOG.md`.
- Web UI is intentionally minimal: no pagination/filter/sort UI, no edit/review/research UI, no graph/chat.

## 下一阶段计划

- Phase 7b / later Web read improvements: graph/detail UX, filtering/sorting/pagination, and human-facing redaction policy.
