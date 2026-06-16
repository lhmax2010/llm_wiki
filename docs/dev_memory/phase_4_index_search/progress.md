# Phase 4 - Index Search / Progress

> 开发过程持续追加，记录思考与决策，而非仅结果。

## 关键决策

- 风险档确认：Phase 4 = 普通风险，两路 review（Claude + ChatGPT）。
  - 原因：P4 是索引/查询层，不改 P1 schema/证据映射，不改 P2 写入治理/权限/audit，也不改 P3 propose wrapper 信任边界。
  - 专项必查 1：`research_index` 是否只做占位，P4 是否没有扫描/索引 `kb/research/`。
  - 专项必查 2：MCP `search_kb` 从直扫切到索引后，是否仍物理不含 research，且 `SearchResult` 字段不缩水。

- 决策：agent/human 真实索引在建索引源头排除 `research/`。
  - 原因：继承 P3 的 research 物理不可见纪律，不能依赖查询时过滤；即使查询 scope/status 过滤有 bug，索引里也没有 research 数据可泄漏。
  - 实现：`SQLiteMetadataIndex(source_dirs=("entries",))` 是 agent/human 默认真实索引来源；`SQLiteMetadataIndex.__post_init__()` 拒绝非 P6 场景下把 `research` 放进 `source_dirs`。
  - 排除的方案：排除先索引所有目录再按 `trust_state != research` 过滤；排除把 `research/` 纳入 human index 的 P4 预实现。

- 决策：`research_index` 是同接口占位，不建真实 research DB。
  - 原因：design §7 明确 research 真实数据与隔离校验属于 P6；P4 逆向实现会破坏 DAG。
  - 实现：`ResearchSearchIndex.rebuild()` 返回 `status="placeholder"`、`indexed_entries=0`；`search()` 恒返回空列表，不扫描 `kb/research/`，不创建 `research_search_index/metadata.sqlite`。
  - 排除的方案：排除 `NotImplementedError` 形式，因为后续调用方/测试需要稳定空实现；排除“建表但不填”的假索引，避免误导为 research 已受 P4 管理。

- 决策：MCP `search_kb` 改为索引优先，P3 直扫作为安全 fallback。
  - 原因：P4 要让 agent 主搜索吃到同义词/CJK/SQLite scope，但索引文件缺失/损坏时仍要保持 P3 可用性。
  - 实现：`MCPHandlers.search_kb()` 先调用 `SearchService.search_agent()`；捕获 `IndexUnavailable` 后记录 warning，并回到原 P3 白名单直扫。fallback 仍只扫 `entries/`，`include_pending=True` 只额外扫 `staging/`。
  - 排除的方案：排除索引不可用直接让 MCP search 失败；排除 fallback 扫 `drafts/` 或 `research/`。

- 决策：pending overlay 先直接扫 `staging/`，不做单独持久索引。
  - 原因：P4 的真实索引消费方主要是已发布 search；pending 内容规模预期小，直接扫 staging 更简单，且沿用 P3 的 include_pending 语义。
  - 排除的方案：排除新增一个 pending SQLite overlay DB，避免 P4 过度设计。

- 决策：索引生成采用显式 rebuild 脚本 + Python API，不做写入时增量更新。
  - 原因：P4 目标是建立检索能力；写入时增量更新需要与 P2 persist/P5 review 生命周期绑定，放在后续优化更稳。
  - 实现：`SearchService.rebuild_agent_index()` / `rebuild_human_index()` / `rebuild_research_index()`，以及 `scripts/rebuild_indexes.py`。
  - 排除的方案：排除在 P2 persist 后自动更新索引，避免索引层反向耦合治理写入链。

## 改动摘要

- `index/`
  - 新增 `types.py`：SearchScope/SearchResult 共享类型。
  - 新增 `sqlite_index.py`：SQLite metadata index、rebuild、indexed paths 读取、source dir 白名单防护。
  - 新增 `search.py`：SearchService、agent/human search、research placeholder、scope/min_support/snippet/sort。
  - 新增 `synonyms.py`：`kb/synonyms.jsonl` 加载与 query expansion。
  - 新增 `cjk.py`：CJK bigram token 与 bigram search match。
- `mcp/kb_server/`
  - `handlers.py`：`search_kb` 索引优先，`IndexUnavailable` 时安全 fallback。
  - `types.py`：复用 `index.types` 的 SearchScope/SearchResult，避免字段分叉。
- `scripts/rebuild_indexes.py`
  - 新增显式 rebuild CLI。
- `tests/index/`
  - 覆盖 agent/human 索引、research 占位、同义词、CJK、min_support、metadata scope、SearchResult 字段完整。
- `tests/mcp/test_handlers.py`
  - 覆盖 MCP `search_kb` 切到索引后可用同义词扩展，并保持 pending overlay 只含 staging。

## 进度日志

- [2026-06-16] 从 main `bb12439fa677cdab472f0294364542c77684afc2` 开分支 `phase/4-index-search`。
- [2026-06-16] 读取 design §4.1.1/§4.1.2/§5.4/§7 Phase 4 与 Phase 3 dev_memory，确认 P4 关键风险是索引层重新打开 research 泄漏口。
- [2026-06-16] 用户确认风险档普通风险；确认 restate 后开始编码。
- [2026-06-16] 实现 `index/` 包与 `scripts/rebuild_indexes.py`，未新增 Python 依赖；本机 `rg --version` 为 `ripgrep 15.1.0`。
- [2026-06-16] 将 MCP `search_kb` 接入 `SearchService.search_agent()`，保留 P3 fallback。
- [2026-06-16] 补测试：research 源头排除、`research_index` placeholder、同义词“绿屏”命中“花屏”、CJK bigram“画面绿屏”命中“画面出现绿屏”、`min_support` 段落穿透、MCP search 索引切换。
- [2026-06-16] 局部测试 `uv run pytest tests/index tests/mcp -q`：功能测试 `29 passed`，但局部跑触发全局 coverage 阈值失败（total 68.46% < 80），非功能失败。
- [2026-06-16] 三道门：
  - `uv run ruff format .` -> `41 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts` -> `Success: no issues found in 41 source files`
  - `uv run pytest --cov --cov-report=term-missing -q` -> `114 passed in 7.72s`
  - Total coverage: `92.11%`

## TODO

- 增量索引更新：后续与 P2 persist/P5 review 生命周期对齐后再做。
- `rg` 候选目前是 best-effort 辅助，正确性仍由 Python Entry 回读与 scope 过滤保证；后续可优化为严格候选集合以提升大库性能。
- `human_search_index` P4 只有接口与真实 rebuild/search，P7 接 Web 时再补人读排序/摘要策略。
