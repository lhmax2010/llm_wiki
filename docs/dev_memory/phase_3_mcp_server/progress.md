# Phase 3 - MCP Server / Progress

> 开发过程持续追加，记录思考与决策，而非仅结果。

## 关键决策

- 风险档确认：Phase 3 = 普通风险，两路 review（Claude + ChatGPT）。
  - 原因：P3 是 MCP wrapper 层，不改 P1 证据映射/schema、不改 P2 权限/发号/audit/review 分级内核、不实现 P6 research 隔离业务。
  - review 专项必查 1：`propose_entry` / `propose_update` 是否完整走 Phase 2 Governed API pipeline 七段，不能在 MCP 层重写或漏段，避免 P2 修过的 role/diff/id/audit 信任边界绕过面回流。
  - review 专项必查 2：`search_kb` 是否物理不扫 `kb/research/`，继承 P1 三态隔离，agent 主搜索不能搜到 research。

- 决策：`propose_update` 缺旧内容时不拒绝请求，按 Phase 2 的保守 heavy 纪律继续走 pipeline。
  - 原因：P2 已规定缺少 `previous_payload` / `previous_entry` 时不能精细降级，只能保守 heavy；P3 wrapper 不引入新拒绝行为，避免 Kona 每次 update 都被迫先 `get_entry` 才能提交。
  - 排除的方案：排除在 MCP wrapper 层直接失败；排除信任调用方自报 diff 降级。

- 决策：`search_kb(include_pending=True)` 只额外包含 `kb/staging/`，不包含 `kb/drafts/`。
  - 原因：`pending` 语义是已进入审核流的条目；`drafts/` 是未提交草稿，不应让 agent 主搜索当作 pending 知识使用。P3 用目录白名单实现：默认 `entries/`，include_pending 时 `entries/ + staging/`，永不包含 `research/`。
  - 排除的方案：排除黑名单过滤 research；排除把 drafts 暴露给 agent 搜索。

- 决策：P3 不新增 MCP SDK 依赖，先实现 transport-agnostic handler + 最小 JSON-RPC stdio wrapper。
  - 原因：当前 Phase 的核心风险在治理复用与可见性边界，handler 纯 Python 更容易单测并避免 R8 新依赖审批；stdio wrapper 覆盖 `initialize`、`tools/list`、`tools/call`，足够完成 P3 端到端验收。
  - 排除的方案：排除在本 Phase 直接引入第三方 MCP SDK；后续若要切官方 SDK，作为独立 R8 依赖决策处理。

- 决策：`propose_entry` / `propose_update` 的 default pipeline 固定为 Phase 2 七段：
  `auth_context -> schema_validate -> evidence_validate -> classify_write_route -> review_route -> persist -> audit_append`。
  - 原因：MCP wrapper 不能重建治理链，否则 Phase 2 已修复的 role/diff/id/audit 信任边界会重新暴露。测试中既有 fake 七段顺序断言，也有真实 pipeline 写盘/audit 验收。
  - 排除的方案：排除 MCP 层直接写 `core.storage.write_entry()`；排除 MCP 层自行发号；排除跳过 `audit_append`。

## 进度日志

- [2026-06-15] 开分支 `phase/3-mcp-server`，baseline `f55509a5e8a9d0d754b80466233854fadbf630c3`。
- [2026-06-15] 读取 design §4.1.1 / §4.4 / §7 Phase 3 与 Phase 2 dev_memory，确认 P3 必须复用 Governed API pipeline，不能重写治理。
- [2026-06-15] 用户确认风险档为普通风险，两路 review；要求 review prompt 将 pipeline 绕过和 research 物理不可见列为专项必查。
- [2026-06-15] 用户确认 restate 后开始编码；明确 `propose_update` 缺旧内容保守 heavy，`include_pending` 只含 staging 不含 drafts。
- [2026-06-15] 完成 `mcp/kb_server/`：handler 核心、TypedDict、最小 JSON-RPC stdio server；未新增业务依赖。
- [2026-06-15] 补 `tests/mcp/`：覆盖 search 白名单隔离、pending 只含 staging、get_entry 完整字段、list/browse 只读 published、propose_entry 七段顺序与真实写盘/audit、propose_update 系统事实 diff、research hints stub、stdio server loop。
- [2026-06-15] 首轮门禁结果：`uv run ruff format .` -> `32 files left unchanged`；`uv run ruff check .` -> `All checks passed!`；`uv run mypy core tests governed-api mcp` -> `Success: no issues found in 32 source files`；`uv run pytest --cov --cov-report=term-missing -q` -> `97 passed in 5.94s`，总覆盖率 `93.15%`，`mcp/kb_server/handlers.py` 覆盖率 `80%`，`mcp/kb_server/server.py` 覆盖率 `62%`。

## TODO

- restate 待用户确认。
