# Phase 4 - Index Search / Result

## 最终状态

待 Review。Phase 4 索引 + 检索 V1 已完成编码与本地门禁；PR #4 已创建，进入两路 review（Claude + ChatGPT）。

## 测试情况

- 静态检查（ruff/mypy）：
  - `uv run ruff format .` -> `41 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts` -> `Success: no issues found in 41 source files`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `114 passed in 7.72s`
  - Total coverage: `92.11%`
  - touched index/mcp coverage snapshot:
    - `index/__init__.py`: `100%`
    - `index/cjk.py`: `100%`
    - `index/search.py`: `84%`
    - `index/sqlite_index.py`: `81%`
    - `index/synonyms.py`: `88%`
    - `index/types.py`: `100%`
    - `mcp/kb_server/handlers.py`: `80%`
    - `mcp/kb_server/types.py`: `100%`
- 集成/端到端验收：
  - Phase 4 无 Web/API E2E。
  - 已用单测覆盖 SQLite metadata rebuild、agent/human search、MCP `search_kb` 索引接入、research 物理不可见、同义词、CJK bigram、`min_support` 段落穿透。

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/4
- 对应 Git Commit：
  - `b20061a` - `[Phase 4] index search layer`

## Review 状态

- 风险档：普通风险。
- Review 方式：Claude + ChatGPT。
- 专项必查：
  - `research_index` 是否只是 placeholder，P4 是否没有扫描/索引 `kb/research/`。
  - MCP `search_kb` 从直扫切到索引后，是否仍物理不含 research，且 agent `SearchResult` 字段不缩水。
- Review prompt：`docs/review/phase_4_review_prompt.md`

## 遗留问题 / 风险

- 写入时增量索引更新未实现；P4 采用显式 rebuild API/脚本，后续可与 persist/review 生命周期对齐。
- `human_search_index` P4 仅实现后端接口与测试，Web/HTTP 消费方留 P7。
- `research_index` 为占位空实现；真实 research 索引、TTL、promote、隔离业务留 P6。
- 语义检索/embedding/LLM rerank 未实现，按 design 属于 V1.5 或后续。

## 下一阶段计划

- Phase 5：staging + review 分级，消费 P3 MCP 与 P4 search 后进入 review 生命周期。
