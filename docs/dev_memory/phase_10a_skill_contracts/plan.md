# Phase 10a - Skill Contracts / Plan

## 目标

把 `kb/skills/ingest_skill.md` 和 `kb/skills/maintenance_skill.md` 从骨架正式化为任意 agent 可加载的行为契约。P10a 只教 agent 如何使用已有 MCP 工具，不新增写入路径，不改 P1-P5 核心。

## 范围边界

做：

- 正式化 `ingest_skill.md`：查重 -> 判 `entry_type` -> 段落骨架 -> evidence 驱动 -> `propose_entry` / `propose_update`。
- 正式化 `maintenance_skill.md`：诊断前查 KB -> 回读条目 -> 对比 `code_binding` -> 用 `propose_update` 标 stale。
- 增加 skill validator，校验 UTF-8 Markdown、必备章节、必备术语、MCP 工具白名单、危险绕治理指令。
- 增加测试，证明真实 skill 可加载，危险表达会失败，正常系统描述不会误伤。
- 增加 Claude review prompt，专项检查“不绕过治理”和“证据驱动，不自报 claim_type”。

不做：

- 不做 P10b 的 Kona 端到端接入验收和 Cline 压测。
- 不新增 MCP 工具，不调用 research opt-in 工具。
- 不改 P1-P5 内容核、治理、MCP、索引、review 发布闸门。
- 不实现新的权限、review、audit、storage 或索引逻辑。

## 计划步骤

1. 重写两份 skill 文档，让流程可执行、契约清楚、只引用 P3 MCP 工具。
2. 添加 `scripts/validate_skills.py`，用纯 stdlib 做结构和危险表达校验。
3. 添加 `tests/skills/test_validate_skills.py` 覆盖真实 skill、UTF-8、工具白名单、危险表达和误伤保护。
4. 写 `docs/review/phase_10a_review_prompt.md`，列出 Claude 一路 review 的专项检查。
5. 更新 `progress.md` / `result.md` / `INDEX.md`。
6. 跑 R13 三道门并提交 PR 分支。

## 依赖

- 依赖 P3 MCP 工具契约：`search_kb` / `get_entry` / `propose_entry` / `propose_update`。
- 依赖 P1/P2/P5 对 `propose_*` 的 schema/evidence/review/audit 治理。
- 无新增 Python 业务依赖。

## 风险档

- 低风险，一路 Claude review。
- 专项必查：
  - skill 是否诱导绕过 P1-P5 治理。
  - skill 是否坚持 evidence -> 系统裁决 `claim_type`，而不是 agent 自报高可信度。

## Baseline

- 分支：`phase/10a-skill-contracts`
- baseline commit：`77f571501b41434a25defb5e8b612ea112074545`
