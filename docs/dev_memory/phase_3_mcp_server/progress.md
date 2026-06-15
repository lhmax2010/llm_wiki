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
- [2026-06-15] Phase 3 review R14：读取项目根 `phase3_fix_instructions.md` 并闭环。根因总纲：两个 BLOCKER 同源于 MCP 层按调用方 id 直接拼路径，缺少 `^KB-\d{4}-\d{4}$` 形状校验和 resolve 后白名单目录确认；这与 P1 三态 `../`、P2 payload id 自报属于同一类“路径/身份事实不能信调用方自报”问题。
- [2026-06-15] R14 修复后门禁结果：`uv run ruff format .` -> `32 files left unchanged`；`uv run ruff check .` -> `All checks passed!`；`uv run mypy core tests governed-api mcp` -> `Success: no issues found in 32 source files`；`uv run pytest --cov --cov-report=term-missing -q` -> `104 passed in 6.17s`，总覆盖率 `93.07%`，`mcp/kb_server/handlers.py` 覆盖率 `80%`，`mcp/kb_server/server.py` 覆盖率 `69%`。

## R14 修复记录

- FIX-1【BLOCKER】：`get_entry` path traversal 可读到 research。
  - 修复思路：新增统一 `KB_ID_RE` / `_validate_entry_id()` / `_entry_path()`；所有按 id 读路径的 MCP 入口先校验 `^KB-\d{4}-\d{4}$`，再 `resolve()`，并确认最终路径仍在白名单目录内。`get_entry` 默认只读 `entries/`，即使 `include_pending=True` 也只扩到 `staging/`，不触碰 `research/`。
  - 测试：`test_get_entry_rejects_path_traversal_and_cannot_read_research`。

- FIX-2【BLOCKER】：`propose_update` 缺旧条目时从 patch 自带 id 继续跑。
  - 修复思路：`propose_update` 先校验入口 id，再读取系统事实旧 entry；`previous_entry is None` 时直接返回 `E_SCHEMA(id): entry not found`，不进入 pipeline；`_merge_update_payload()` 即使未来被复用也强制 `payload["id"] = entry_id`，不信 patch 自带 id。
  - 测试：反转旧测试为 `test_propose_update_without_previous_entry_fails_and_ignores_patch_id`，并补 `test_propose_update_rejects_invalid_id_before_path_use`。

- FIX-3【MAJOR】：坏 `.md` 拖垮读工具。
  - 修复思路：`_read_entries_from_dir()` 逐文件 `try/except`，坏 entry 记录 warning 后跳过；这是读索引容错，区别于 SQLite 发号重建的 fail-loud。
  - 测试：`test_read_tools_skip_bad_markdown_and_log_warning` 覆盖 search/list/browse 继续返回好条目并记录日志。

- FIX-4【MAJOR】：server JSON 解析在 try 外崩溃。
  - 修复思路：`handle_jsonrpc_line()` 将 `json.loads()` 纳入 try，`JSONDecodeError` 返回 JSON-RPC `-32700` parse error；`run_stdio_server()` 外层兜底，单条坏请求不杀循环。
  - 测试：`test_invalid_json_returns_parse_error_and_loop_continues`。

- FIX-5【MINOR】：协议层未捕获未知异常。
  - 修复思路：`handle_jsonrpc_line()` 对未预期异常记录 exception 并返回 `-32603` internal error；stdio loop 也有外层 `-32603` 兜底。
  - 测试：`test_unexpected_tool_exception_returns_internal_error`。

- FIX-6【MINOR】：`get_entry` 未按 `include_pending` 分级。
  - 修复思路：`get_entry(id, include_pending=False)` 默认只读 `entries/`；`include_pending=True` 才读 `entries/ + staging/`。
  - 测试：`test_get_entry_include_pending_controls_staging_visibility`。

- FIX-7【MINOR】：`sort=updated_desc` 语义错误。
  - 修复思路：search 内部保留 `(Entry, SearchResult)` 对，`updated_desc` 用 `Entry.updated` 再按 id 排序，不再用 id 冒充更新时间。
  - 测试：`test_search_updated_desc_sorts_by_updated_timestamp`。

## TODO

- limit 上限/类型校验：后续给 `limit` 做 clamp 和输入类型校验。
- IDAllocator 复用：当前每次 build handler/propose 可新建 allocator，功能正确但可做性能优化。
- search 子目录：P3 当前 flat `.md` 扫描，后续若 entries 分层再改 `rglob` 或文档化目录约束。
- MCP `inputSchema` 当前 `additionalProperties: true`，后续补严格 JSON Schema。
- `possible_duplicates` / `E_DUP` 当前恒空，后续 Phase 补重复检测。
- NIT：`_require` 里 `read_published` 占位、读写鉴权语义一致性、`SearchResult.stale` 是 P3 扩展需后续文档化。
