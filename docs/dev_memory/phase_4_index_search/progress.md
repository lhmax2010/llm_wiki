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
  - 实现：`MCPHandlers.search_kb()` 先调用 `SearchService.search_agent()`；捕获 `IndexUnavailable` 后记录 warning，并调用 `SearchService.search_agent_direct()`。fallback 仍只扫 `entries/`，`include_pending=True` 只额外扫 `staging/`，并复用同义词/CJK/min_support 逻辑。
  - 排除的方案：排除索引不可用直接让 MCP search 失败；排除 fallback 扫 `drafts/` 或 `research/`。

- 决策：pending overlay 先直接扫 `staging/`，不做单独持久索引。
  - 原因：P4 的真实索引消费方主要是已发布 search；pending 内容规模预期小，直接扫 staging 更简单，且沿用 P3 的 include_pending 语义。
  - 排除的方案：排除新增一个 pending SQLite overlay DB，避免 P4 过度设计。

- 决策：索引生成采用显式 rebuild 脚本 + Python API，不做写入时增量更新。
  - 原因：P4 目标是建立检索能力；写入时增量更新需要与 P2 persist/P5 review 生命周期绑定，放在后续优化更稳。
  - 实现：`SearchService.rebuild_agent_index()` / `rebuild_human_index()` / `rebuild_research_index()`，以及 `scripts/rebuild_indexes.py`。
  - 排除的方案：排除在 P2 persist 后自动更新索引，避免索引层反向耦合治理写入链。

- R14 决策：按方向 B 修正索引定位，删掉“装饰性加速”。
  - 原因：review 指出 SQLite metadata 列没有参与 WHERE，ripgrep 候选跑完即丢弃，容易让 P4 看起来像在加速但实际没有。与其保留假加速，不如诚实地把 P4 定位为正确性 + 隔离 + 搜索质量层。
  - 实现：SQLite 只保存 validated path catalog（`id/path/source_dir`）；查询时全量回读 Entry 并用 Python 完成 scope、同义词、CJK、`min_support`。千级条目内满足当前性能预算，SQL 过滤/ripgrep 候选优化留后续。
  - 排除的方案：排除继续保留未使用 metadata 列和 ripgrep 空跑；排除本次赶做方向 A 的真 SQL/ripgrep 加速，避免扩大 P4。

## 改动摘要

- `index/`
  - 新增 `types.py`：SearchScope/SearchResult 共享类型。
  - 新增 `sqlite_index.py`：SQLite validated path catalog、rebuild、indexed paths 读取、source dir 白名单防护。
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
- [2026-06-16] Phase 4 review R14：读取外层 `phase4_fix_instructions.md` 并闭环。根因总纲：P4 自己开了新读路径（rebuild 扫目录 + fallback 直扫），没有继承 P1 `validate_entry` 三态一致性和 P3 `resolve/is_relative_to` 路径防护；任何新增读 `kb/` 目录的路径都必须复用这两道防护。
- [2026-06-16] R14 修复后门禁：
  - `uv run ruff format .` -> `41 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts` -> `Success: no issues found in 41 source files`
  - `$env:PYTHONWARNINGS='error::ResourceWarning'; uv run pytest tests\index -q --no-cov` -> `12 passed in 0.80s`
  - `uv run pytest --cov --cov-report=term-missing -q` -> `120 passed in 7.63s`
  - Total coverage: `93.56%`

## R14 修复记录

- FIX-1【BLOCKER】：symlink 绕过源目录白名单，research 内容进 agent 索引。
  - 修复思路：`read_valid_entry_file()` 在读文件前 `resolve(strict=True)`，并确认 resolved path 仍在 source root 内；逃逸 symlink 跳过并 warning，不读、不索引。
  - 测试：`test_agent_index_rebuild_rejects_symlink_escape_to_research`。

- FIX-2【BLOCKER】：坏 `trust_state` 文件被 agent 搜到。
  - 修复思路：rebuild、indexed read、direct fallback、MCP scan/get_entry 都走 `validate_entry(..., kb_root=..., entry_path=..., check_evidence_exists=False)`；三态不一致产生 E_SCHEMA 后跳过或返回 E_SCHEMA，不进入搜索结果。
  - 测试：`test_agent_index_rebuild_skips_entry_with_wrong_trust_state`、`test_search_kb_fallback_skips_entry_with_wrong_trust_state`。

- FIX-3【MAJOR】：SQLite 连接未显式关闭。
  - 修复思路：`sqlite3.connect(...)` 统一包 `contextlib.closing(...)`，写路径显式 `commit()`，对齐 P1 IDAllocator 模式。
  - 验证：`PYTHONWARNINGS=error::ResourceWarning` 下 `tests/index` 通过。

- FIX-4【MAJOR】：索引是装饰，ripgrep 空跑和未使用 metadata 列误导。
  - 修复思路：采用方向 B。删除 ripgrep 空跑；SQLite 只保存 path catalog；代码注释和 dev_memory 明确 P4 保证正确性/隔离/搜索质量，性能优化留后续。
  - 测试：原同义词/CJK/min_support 测试保留，证明搜索质量能力不受删除装饰影响。

- FIX-5【MINOR】：fallback 无同义词/CJK，召回静默退化。
  - 修复思路：MCP fallback 改为 `SearchService.search_agent_direct()`，与索引路径共享同义词/CJK/min_support/filter/sort 实现。
  - 测试：`test_search_kb_fallback_reuses_synonym_and_cjk_matching`。

- FIX-6【MINOR】：`synonyms.jsonl` 坏行导致整体失败。
  - 修复思路：逐行 `try/except`，坏 JSON 或坏 schema warning 后跳过，不影响好行。
  - 测试：`test_bad_synonym_line_is_skipped_without_disabling_good_lines`。

- FIX-7【MINOR】：异常 source_dir 抛 ValueError 而非 IndexUnavailable。
  - 修复思路：indexed read 发现 DB row 的 source_dir 非法时归一成 `IndexUnavailable`，让 MCP search 能走降级路径。
  - 测试：`test_index_read_entries_normalizes_invalid_source_dir_to_index_unavailable`。

## TODO

- 增量索引更新：后续与 P2 persist/P5 review 生命周期对齐后再做。
- 索引陈旧检测：离线 rebuild 后，新发布条目要等 rebuild 才可见；后续加 staleness 告警或写后触发 rebuild。
- 性能优化：后续按真实规模引入 SQL 层过滤或 ripgrep 候选集合；P4 只保证千级条目内全量回读可用。
- CJK bigram 精度：后续补负向测试并考虑收紧跨句/半重合命中。
- `SearchService` 属性每次新建 index 实例，后续可缓存。
- `human_search_index` P4 只有接口与真实 rebuild/search，P7 接 Web 时再补人读排序/摘要策略。
