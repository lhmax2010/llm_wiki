# Phase 10a Review Prompt - Skill Contracts

请对 Phase 10a PR 做低风险一路 review（Claude）。重点不是找核心代码 bug，而是检查 skill 契约是否符合统一知识库的治理纪律。

## 背景

P1-P5 已经建立内容核、Governed API、MCP wrapper、索引检索和 staging review 发布闸门。P10a 只正式化 `kb/skills/ingest_skill.md` 与 `kb/skills/maintenance_skill.md`，让任意 agent 知道如何通过已有 MCP 工具沉淀和维护知识。

## 本 Phase 范围

- `ingest_skill.md`：查重 -> 判 `entry_type` -> 段落骨架 -> evidence 驱动 -> `propose_entry` / `propose_update`。
- `maintenance_skill.md`：诊断前 `search_kb` -> `get_entry` 回读 -> 对比 `code_binding` -> `propose_update` 标 stale。
- `scripts/validate_skills.py`：校验 UTF-8 Markdown、必备章节、必备术语、MCP 工具白名单、危险绕治理表达。
- `tests/skills/test_validate_skills.py`：覆盖真实 skill、危险表达、误伤保护和工具白名单。

## 专项必查 1：skill 是否绕过治理

请重点检查：

- skill 是否只让 agent 使用 `search_kb` / `get_entry` / `propose_entry` / `propose_update`。
- 是否有任何措辞诱导 agent 直接写 `kb/entries`、`kb/staging`、SQLite、audit、index 或 review 队列。
- 是否有任何新写入路径绕开 P2 pipeline / P5 review。
- validator 是否能抓住明显绕治理指令，并避免误伤正常系统描述或禁止事项。

## 专项必查 2：是否坚持 evidence 驱动

请重点检查：

- skill 是否明确“agent 提供 evidence，系统裁决 `claim_type` / `support_strength`”。
- 是否有措辞诱导 agent 自报 `fact` / `spec` / 高可信度来压过系统裁决。
- 是否要求 agent 读取并处理 `warnings` / `errors`，接受降级和打回。
- maintenance 的 stale 更新是否要求具体 evidence 和 `stale_reason`，而不是泛泛“可能过期”。

## 明确不做

- 不做 P10b Kona E2E / Cline 压测。
- 不改 P1-P5 核心。
- 不新增 MCP 工具。
- 不实现 research opt-in 业务。

## 验证命令

- `uv run ruff format . --check`
- `uv run ruff check .`
- `uv run mypy core tests governed-api mcp index scripts review`
- `uv run pytest --cov --cov-report=term-missing -q`

## 输出格式

请按严重度输出：

- `[BLOCKER]`：会导致 skill 绕过治理、错误诱导 agent、或证据纪律失效。
- `[MAJOR]`：会让 agent 行为不稳定、契约不清、validator 漏掉关键风险。
- `[MINOR]`：可改进但不阻塞。
- `[NIT]`：措辞或格式小问题。
