# Phase 10a - Skill Contracts / Progress

## 关键决策

- P10a 是行为契约，不是新功能层。两份 skill 只指导 agent 调 P3 MCP 工具，不新增文件写入、review、audit、storage 或索引路径。
- 证据纪律写成硬规则：agent 只提供 evidence 和候选内容，`claim_type` / `support_strength` 由 P2 `evidence_validate` 和后续 review 裁决。skill 要求 agent 读取 `warnings` / `errors`，接受降级或打回。
- validator 的危险表达检测只抓“祈使/授权 agent 绕过治理”的表达，例如“请直接写入 kb/entries”“应该绕过 review”。它不会因为正常描述 `entries` / `staging` 或禁止事项里的“不要直接改”而失败，避免误伤合理说明。
- P10a 不引用 research opt-in 工具。maintenance 只处理已通过 `search_kb` / `get_entry` 可见的 KB 条目，research 业务留给 P6/P10b。

## 排除方案

- 不把 `kb/skills` 改成 Codex `SKILL.md` 目录结构：本项目需要通用 Markdown 行为契约，面向任意 agent，而不是绑定某个 agent runtime。
- 不做复杂自然语言安全分类器：P10a 只需要可解释、可测试的规则护栏；更复杂的 agent 安全评估留给接入验收。
- 不让 skill 直接描述如何操作文件系统或 DB：这会绕开 P1-P5 治理链路，违反专项必查。

## TODO

- [待 review] Claude review 检查 skill 措辞是否真的坚持 evidence 驱动，validator 是否有漏掉的绕治理表达。
