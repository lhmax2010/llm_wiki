# Phase 10a - Skill Contracts / Progress

## 关键决策

- P10a 是行为契约，不是新功能层。两份 skill 只指导 agent 调 P3 MCP 工具，不新增文件写入、review、audit、storage 或索引路径。
- 证据纪律写成硬规则：agent 只提供 evidence 和候选内容，`claim_type` / `support_strength` 由 P2 `evidence_validate` 和后续 review 裁决。skill 要求 agent 读取 `warnings` / `errors`，接受降级或打回。
- validator 的危险表达检测目标是“skill 被污染后诱导 agent 绕过治理”。检测必须抓祈使/授权表达，也要抓裸命令；同时不能误伤明确禁止句和正常系统描述。
- P10a 不引用 research opt-in 工具。maintenance 只处理已通过 `search_kb` / `get_entry` 可见的 KB 条目，research 业务留给 P6/P10b。

## R14 根因

- 三路 review 一致认为 skill 文档本身不用改，证据驱动方向和无后门措辞成立。
- validator 仍有三个 MAJOR：过度豁免“裸不/只能”、只检查 known MCP 工具、危险表达过度依赖祈使前缀。这会让污染后的 skill 用换说法绕过守门员。

## R14 修复

- FIX-1：收窄禁止句豁免。移除裸 `不` / `只能` / `只允许` 豁免；改成只在危险 match 附近出现明确禁止式（如 `不要` / `不得` / `禁止` / `不允许` / `不直接` / `不跳过`）才豁免。因此 `不妨直接写 kb/entries`、`只能直接写 kb/staging` 会被 flag，而 `不要自报高可信度`、`不直接改 KB 文件` 不会误伤。
- FIX-2：工具检测从 known-list 改为任意 `xxx(...)` 函数调用白名单。只允许 `search_kb` / `get_entry` / `propose_entry` / `propose_update`；`write_kb(...)`、`approve_staging_entry(...)` 等虚构或内部工具都会报 `E_TOOL`。
- FIX-3：危险表达检测支持裸命令，不再必须出现 `请/必须/应该` 前缀；补充敏感目标 `drafts` / `research` / `trust_state` / `frontmatter`，补充绕过对象 `查重` / `权限` / `RBAC` / `evidence_validate` / `schema_validate`，补充自报可信度对象 `support_strength` / `标注` / `标记为`。

## 排除方案

- 不把 `kb/skills` 改成 Codex `SKILL.md` 目录结构：本项目需要通用 Markdown 行为契约，面向任意 agent，而不是绑定某个 agent runtime。
- 不做复杂自然语言安全分类器：P10a 只需要可解释、可测试的规则护栏；更复杂的 agent 安全评估留给接入验收。
- 不让 skill 直接描述如何操作文件系统或 DB：这会绕开 P1-P5 治理链路，违反专项必查。

## TODO

- [后续] m4 正向守护：补充“skill 必须积极要求 evidence 驱动”的更强校验，而不只抓负向危险表达。
- [后续] 跨行绕过：当前 validator 是逐行规则，`直接写` 与 `kb/entries` 被拆成两行时仍需更强检测。
- [后续] CI 集成：把 `uv run python scripts/validate_skills.py` 纳入仓库 CI/status check，避免 skill 后续被污染。
- [后续] maintenance 的 `git_sha` 判断和 propose result 字段说明可在 P10b agent E2E 中继续打磨；不阻塞 P10a。
