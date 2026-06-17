# Phase 7a - Web Readonly / Result

## 当前状态

待 review。Phase 7a read-only HTTP API + React minimal frontend 已实现，Python/Frontend gates 与本机 Web smoke 已通过。PR #8 待三路 review（Claude + ChatGPT + Codex HTTP 实测）。

## 已实现

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

## 当前测试快照

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

## PR 与代码

- PR link: https://github.com/lhmax2010/llm_wiki/pull/8
- Commits:
  - `969e571` - `[Phase 7a] web readonly HTTP API + React`
  - docs follow-up: see PR head
- Review prompt: `docs/review/phase_7a_review_prompt.md`

## 遗留问题 / 风险

- Full npm audit reports dev-toolchain high vulnerabilities; `npm audit --omit=dev` reports `0 vulnerabilities`.
- FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass.
- Web UI is intentionally minimal: no pagination/filter/sort UI, no edit/review/research UI, no graph/chat.
