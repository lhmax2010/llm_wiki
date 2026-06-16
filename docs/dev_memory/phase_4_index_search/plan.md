# Phase 4 - Index Search / Plan

## 目标

实现 design §7 Phase 4 的索引与检索层：建立多索引基础设施，完成
`agent_search_index` 与 `human_search_index` 两个真实索引，并支持 SQLite
结构化元数据过滤、正文检索、`kb/synonyms.jsonl` 同义词扩展、CJK bigram
匹配与 `min_support` 段落穿透。

P4 还要把 Phase 3 的 `search_kb` 从 storage 直扫版衔接到索引层，同时保持
Phase 3 已经守住的两个边界：agent 主搜索物理不含 `research/`，返回的 agent
视图字段不丢。

## 范围边界

### 本阶段做

- 在 `index/` 下建立可测试的 Python 索引模块。
- 建立三索引框架：
  - `agent_search_index`：真实索引，只纳入 `kb/entries/`，可选由 MCP
    `include_pending=True` 时叠加 pending 查询路径，但默认 agent 主搜索物理不含
    `research/`。
  - `human_search_index`：真实索引，面向人读搜索；P4 只索引已提交内容，不实现
    P6 research 业务。
  - `research_index`：仅接口占位/空实现，返回空结果或明确未构建状态，不扫描
    `kb/research/`，不写 research 真实索引数据。
- SQLite 元数据索引：索引 `id`、`title`、`module`、`entry_type`、`trust_state`、
  `claim_type`、`support_strength`、`error_codes`、`tags`、`stale`、`updated` 等搜索过滤字段。
- 正文检索：优先复用 ripgrep 做正文候选查找；结果再回读 Entry 生成结构化
  `SearchResult`，保持 `credibility`、`trust_state`、`matched_section`、`stale` 等字段。
- 同义词扩展：读取 `kb/synonyms.jsonl`，`expand_synonyms=True` 时将 canonical 与 synonyms
  作为查询词集合参与匹配。
- CJK bigram：为中文查询和内容生成 bigram token，补足纯子串/ripgrep 对中文短词的覆盖。
- `min_support` 段落穿透：entry 级 support 不满足时，任一 section 级 support 达标也命中，并返回
  `matched_section`。
- 将 MCP `search_kb` 衔接到索引层；索引不可用时 fallback 到 P3 直扫逻辑，但 fallback
  仍只能扫白名单目录，不能碰 `research/`。
- 补 UT 覆盖索引构建、查询、同义词、CJK、`min_support`、research 物理不可见、
  `research_index` 占位，以及 MCP search 切换后不破坏 P3 边界。

### 本阶段不做

- 不实现 research 真实索引、research 搜索、TTL、promote、research 不能作 evidence 等 P6 业务。
- 不把 `kb/research/` 纳入 `agent_search_index` 或 `human_search_index`。
- 不实现 Web 搜索 UI、HTTP API handler、Chat UI 或图谱 UI；P7 再接入人读界面。
- 不实现 staging/review 流转、review 队列和审批 UI；P5 负责。
- 不引入语义检索、embedding、LLM rerank 或外部搜索服务。
- 不重写 Phase 1 schema/validation 或 Phase 2 governed pipeline。

## 计划步骤

1. 记录 baseline commit 与 P4 风险档，等待用户确认风险档和 restate 后再编码。
2. 读取 Phase 3 `search_kb` 直扫实现，抽出可复用的 SearchResult 组装/排序/范围过滤逻辑，
   避免索引层返回字段缩水。
3. 设计 `index/` 模块接口：索引构建、索引查询、同义词加载、CJK token、research 占位索引。
4. 实现 SQLite 元数据索引 schema 与 rebuild 流程；索引来源按索引类型白名单目录决定。
5. 实现 query pipeline：查询扩展 -> 正文/metadata 候选 -> scope 过滤 -> support 穿透 ->
   snippet/score/sort/limit/offset。
6. 将 MCP `search_kb` 切到索引层；索引缺失或不可读时走安全 fallback。
7. 补单测和集成测试，重点证明 research 目录不会被索引或 fallback 搜到。
8. 运行三道门并记录真实输出到 `progress.md`；产出 review prompt，专项检查 research 隔离与
   P3 search 衔接。

## 依赖前置阶段

- Phase 1：`core.models`、`core.storage`、三态目录一致性、Entry schema 与 `section_credibility`。
- Phase 2：治理层与 RBAC 已完成；P4 本身不改写链路，但后续 Web/MCP 查询会复用同一内容核。
- Phase 3：MCP `search_kb` 直扫版、agent 视图字段完整性、research 物理不可见边界。

## 依赖决策

- 预期不新增 Python 业务依赖：SQLite 使用标准库 `sqlite3`；正文检索调用系统 `ripgrep`。
- 如果编码阶段发现需要新增 Python 包或系统依赖配置，按 R8 暂停报批。

## Baseline

- 分支：`phase/4-index-search`
- baseline commit：`bb12439fa677cdab472f0294364542c77684afc2`
