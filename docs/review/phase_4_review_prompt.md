# Phase 4 Review Prompt - Index Search

请对 Phase 4 PR 做代码审查。风险档：普通风险，两路 review（Claude + ChatGPT）。

PR 链接：https://github.com/lhmax2010/llm_wiki/pull/4

## 背景

本项目是内网统一知识库。Phase 1 已完成内容核/schema/storage/validation；Phase 2 已完成 Governed API pipeline 并修复 role/diff/id/audit 信任边界；Phase 3 已完成 MCP wrapper，并修复 path traversal 读 research 与 `propose_update` 绕发号问题。

Phase 4 是索引 + 检索层：实现 agent/human 两个真实索引、同义词、CJK bigram、`min_support` 段落穿透，并把 MCP `search_kb` 从 P3 直扫切到索引优先。

## 本次范围

- 新增 `index/`：
  - `sqlite_index.py`：SQLite metadata index 与 rebuild。
  - `search.py`：SearchService、agent/human search、research placeholder。
  - `synonyms.py`：`kb/synonyms.jsonl` 加载和 query expansion。
  - `cjk.py`：CJK bigram。
  - `types.py`：SearchScope/SearchResult。
- 新增 `scripts/rebuild_indexes.py`。
- 修改 `mcp/kb_server/handlers.py`：`search_kb` 索引优先，索引不可用时 fallback 到 P3 安全直扫。
- 修改 `mcp/kb_server/types.py`：SearchScope/SearchResult 复用 index types。
- 新增 `tests/index/` 与 MCP search 索引接入测试。

## 专项必查 1：research 是否从建索引源头排除

重点检查：

- `agent_search_index` / `human_search_index` 的 source dirs 是否只来自白名单目录。
- `kb/research/` 是否没有进入 SQLite metadata index。
- `research_index` 是否只是 placeholder：
  - `rebuild()` 不扫描 `kb/research/`。
  - `search()` 返回空列表。
  - 不创建/填充真实 research metadata DB。
- 是否存在任何“先索引 research 再按 trust_state/status 过滤”的路径。
- 测试是否证明即使 `kb/research/` 有匹配内容，agent/human/research placeholder 都不会返回它。

如果发现 P4 任何真实索引扫描或保存了 `kb/research/` 内容，请标为 BLOCKER。

## 专项必查 2：MCP search 切索引后是否破坏 P3 边界

重点检查：

- `MCPHandlers.search_kb()` 是否优先调用 Phase 4 `SearchService.search_agent()`。
- 索引不可用 fallback 是否仍只扫 `entries/`，`include_pending=True` 只额外扫 `staging/`。
- fallback 是否没有扫 `drafts/` 或 `research/`。
- 索引返回的 `SearchResult` 字段是否不比 P3 少：`id/title/entry_type/module/snippet/matched_section/credibility/trust_state/stale/score`。
- `get_entry` 是否仍走 P3 完整 Entry 读取逻辑，没有被索引摘要替代。

如果发现 MCP search 可通过索引或 fallback 搜到 research，请标为 BLOCKER。

## 其他审查点

- 同义词扩展是否真正由 `kb/synonyms.jsonl` 驱动，测试是否证明搜“绿屏”能命中“花屏”条目。
- CJK bigram 是否参与真实 search 命中，测试是否不是只测 helper。
- `min_support` 是否支持 entry 级或任一 section 级满足即命中，并返回 `matched_section`。
- SQLite metadata index 是否可重建，坏 Markdown 是否容错跳过并记录日志。
- `human_search_index` 是否没有过度提前实现 P7/Web 行为。
- P4 是否没有引入语义检索、embedding、LLM rerank 或新业务依赖。

## 已跑门禁

- `uv run ruff format .` -> `41 files left unchanged`
- `uv run ruff check .` -> `All checks passed!`
- `uv run mypy core tests governed-api mcp index scripts` -> `Success: no issues found in 41 source files`
- `uv run pytest --cov --cov-report=term-missing -q` -> `114 passed in 7.72s`
- Total coverage: `92.11%`

## 输出格式

请按严重程度输出：

- `[BLOCKER]`：合并前必须修。
- `[MAJOR]`：原则上必须修，不修需明确放行。
- `[MINOR]`：可记 TODO。
- `[NIT]`：可选。

每条请包含文件/函数、问题、可复现路径或失败场景、建议修法。
