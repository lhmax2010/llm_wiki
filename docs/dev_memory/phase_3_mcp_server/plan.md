# Phase 3 - MCP Server / Plan

## 目标

实现 agent 层 MCP server：提供 design §4.1.1 的 6 个标准工具
`search_kb` / `get_entry` / `list_categories` / `browse` / `propose_entry` /
`propose_update`，以及可选工具 `search_research_for_hints` 的 P3 stub。

P3 的核心目标是让 Kona 等 agent 能通过 MCP 读取同一份内容核，并通过
Phase 2 Governed API pipeline 提交新建/更新提案；MCP 只做入口包装，不复制治理逻辑。

## 范围边界

### 本阶段做

- 在 `mcp/` 下建立 MCP server 模块和可测试的 handler 层。
- 读工具：
  - `search_kb(query, scope?, include_pending?, expand_synonyms?, limit?, offset?, sort?)`
  - `get_entry(id)`
  - `list_categories()`
  - `browse(module, entry_type?)`
- 写工具：
  - `propose_entry(draft, credibility, request_id)`
  - `propose_update(id, patch, reason, credibility?, request_id)`
- research opt-in stub：
  - `search_research_for_hints(query)` 返回 `{"research_signals": []}`，不读取/写入 research。
- `propose_entry` / `propose_update` 必须调用 Phase 2 的 `run_pipeline(...)` 和七段 middleware。
- `get_entry` 返回完整结构化 Entry，包括 `credibility.claim_type`、`support_strength`、`evidence`、
  `code_binding`、`section_credibility`、`code_binding.stale` 等 agent 诊断字段。
- `search_kb` 在 P4 索引尚未实现前使用 storage 直扫作为临时数据源：默认只扫 `kb/entries/`，
  `include_pending=True` 时可额外扫 `kb/staging/`；物理不扫 `kb/research/`，也不把未提交的
  `kb/drafts/` 当作 pending 暴露给 agent。
- 补 UT 覆盖 7 个工具 handler、pipeline 复用、agent 视图字段完整性、research 物理不可见。

### 本阶段不做

- 不实现 P4 的持久索引、同义词扩展、CJK 分词、复杂 ranking 或 `agent_search_index`。
- 不实现 P5 的 review 队列、审批流、Web review UI。
- 不实现 P6 的 research 隔离业务逻辑、research 搜索、research promotion。
- 不碰 Web、collector、frontend。
- 不重新实现 Phase 1 schema/evidence 校验或 Phase 2 role/diff/id/audit 治理。

## 初步接口计划

- `search_kb(...) -> list[SearchResult]`：
  P3 以结构化 dict 返回，字段至少包含 `id`、`title`、`module`、`entry_type`、`trust_state`、
  `claim_type`、`support_strength`、`stale`、`score`、`snippet`。scope 支持
  `module`、`entry_type`、`error_code`、`claim_type`、`min_support`、`exclude_stale`、`status`。
- `get_entry(id) -> dict`：
  通过 `core.storage.read_entry()` 读取并 `model_dump(mode="json")` 返回完整 Entry。
- `list_categories() -> dict`：
  从 published entries 直扫聚合 module、entry_type、tags、error_codes。
- `browse(module, entry_type?) -> dict`：
  返回 published entries 中指定 module 下条目摘要列表，可选 entry_type 过滤。
- `propose_entry(draft, credibility, request_id) -> dict`：
  组装 `MiddlewareContext(operation="propose_entry")`，跑 Phase 2 pipeline，返回 `proposed_id`、
  `status="pending"`、validation 信息和 review level。
- `propose_update(id, patch, reason, credibility?, request_id) -> dict`：
  读取旧 entry 作为系统事实，合并 patch 后跑 Phase 2 pipeline；自报 diff 只升不降，沿用 P2 纪律。
- `search_research_for_hints(query) -> dict`：
  P3 仅权限/签名/stub，返回空 `research_signals`。

## 计划步骤

1. 补 Phase 3 dev_memory 初始留痕，确认风险档与 restate。
2. 读取 P2 pipeline/roles/storage 接口，定义 MCP handler 输入输出类型。
3. 实现 `mcp/` 下纯 handler 核心，保持与 MCP transport 解耦，便于单测。
4. 实现 MCP server thin wrapper（如需第三方 MCP SDK，按 R8 单独报依赖再安装）。
5. 写读工具直扫 storage 的 V1 实现，确保默认不触碰 `kb/research/`。
6. 写 propose 工具，强制经 P2 Governed API pipeline；失败时透传 `ApiError`。
7. 补 UT 和 P3 端到端验收：起 handler/server 调通 6 标准工具 + stub。
8. 运行三道门并把真实命令/输出写入 `progress.md`。

## 依赖前置阶段

- Phase 1：`core.models` / `core.storage` / schema 与 evidence 校验。
- Phase 2：Governed API pipeline、RBAC YAML、audit append、persist、role/diff/id/audit 信任边界。
- 待编码前 R8 确认：是否加入 Python MCP SDK 作为 server transport 依赖；handler 核心先按纯 Python 设计。

## Baseline

- 分支：`phase/3-mcp-server`
- baseline commit：`f55509a5e8a9d0d754b80466233854fadbf630c3`
