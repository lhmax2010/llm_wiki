# Phase 3 Review Prompt - MCP Server

请对 Phase 3 PR 做代码审查。风险档：普通风险，两路 review（Claude + ChatGPT）。

## 背景

本项目是内网统一知识库。人通过 Web/API 读写，agent（如 Kona 缺陷诊断系统）通过 MCP 读写，同一份内容核。Phase 1 已实现内容核/schema/storage/validation；Phase 2 已实现 Governed API middleware pipeline，并修复 role/diff/id/audit 四类信任边界 BLOCKER。Phase 3 是 MCP wrapper 层，不应重写治理逻辑。

## 本次范围

- 新增 `mcp/kb_server/`：
  - `handlers.py`：7 个 MCP 工具的 transport-agnostic handler。
  - `server.py`：最小 JSON-RPC stdio wrapper，支持 `initialize` / `tools/list` / `tools/call`。
  - `types.py`：P3 TypedDict。
- 新增 `tests/mcp/` 覆盖 handler 与 stdio server loop。
- 更新 Phase 3 dev_memory。

## 专项必查 1：MCP wrapper 是否绕过 Phase 2 pipeline

重点检查：

- `propose_entry` / `propose_update` 是否完整调用 Phase 2 Governed API pipeline。
- 默认 middleware 顺序是否固定为：
  `auth_context -> schema_validate -> evidence_validate -> classify_write_route -> review_route -> persist -> audit_append`
- MCP 层是否有任何重新实现/绕过：
  - role 解析或权限自判
  - changed_fields/change_scopes 信任调用方自报来降级 review
  - payload 自带 id 或 MCP 层自行发号
  - 直接 `core.storage.write_entry()` 写盘
  - 漏掉 audit 或 audit 失败未处理
- `propose_update` 是否用系统事实（旧 entry）构造 `previous_entry`，缺旧内容时是否只保守 heavy，不信自报 diff 降级。

如果发现 MCP wrapper 绕过 P2 七段 pipeline，请标为 BLOCKER。

## 专项必查 2：research 物理不可见

重点检查：

- `search_kb` 是否使用目录白名单，而不是黑名单。
- 默认是否只扫 `kb/entries/`。
- `include_pending=True` 是否只额外扫 `kb/staging/`，不扫 `kb/drafts/`。
- 是否任何路径会扫到 `kb/research/`。
- `get_entry` 是否只允许读取 `entries/` 和 `staging/`，不读取 `research/`。
- `search_research_for_hints` 在 P3 是否只是 stub，返回空 `research_signals`，不读写 research 业务。

如果发现 agent 主搜索或 get_entry 能物理读到 research，请标为 BLOCKER。

## 其他审查点

- 6 标准工具 + `search_research_for_hints` 签名是否对齐 design §4.1.1。
- `get_entry` 是否返回完整结构化 Entry，不能裁掉 `claim_type` / `support_strength` / `evidence` / `code_binding` / `section_credibility` / `stale`。
- P3 search 在 P4 索引未实现前的 storage 直扫是否边界清楚，不假装已有 ranking/synonyms/CJK。
- read 工具权限是否至少要求 `read_published`；research hints 是否要求 `search_research_for_hints`。
- `tools/list` / `tools/call` wrapper 是否有明显 JSON-RPC 错误处理问题。
- 测试是否覆盖上述专项风险。

## 已跑门禁

- `uv run ruff format .` -> `32 files left unchanged`
- `uv run ruff check .` -> `All checks passed!`
- `uv run mypy core tests governed-api mcp` -> `Success: no issues found in 32 source files`
- `uv run pytest --cov --cov-report=term-missing -q` -> `97 passed in 5.94s`
- Total coverage: `93.15%`

## 输出格式

请按严重程度输出：

- `[BLOCKER]`：合并前必须修。
- `[MAJOR]`：原则上必须修，不修需明确放行。
- `[MINOR]`：可记 TODO。
- `[NIT]`：可选。

每条请包含文件/函数、问题、可复现路径或失败场景、建议修法。
