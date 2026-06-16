# 入库 Skill（行为契约）

面向任意接入统一知识库的 agent。你要沉淀知识时，只能通过 MCP 工具提交候选内容，让 P1-P5 的内容核、治理、review 流程裁决最终状态。

## 目标

- 把一次诊断、排障规则、代码理解或日志基线整理成可审的 KB 条目。
- 先查重，再决定 `propose_update` 还是 `propose_entry`，避免制造重复知识。
- 提供 evidence，让系统的 `evidence_validate` 裁决 `claim_type` 和降级/打回结果。
- 读取并处理接口返回的 `warnings` / `errors`，不要忽略治理反馈。

## 适用场景

- 缺陷定位后，要沉淀 root cause、修复方式、复现证据或排查经验。
- 发现现有条目可补充、纠错、标记 stale，或需要追加新证据。
- 梳理代码路径、状态机、日志含义、错误码或稳定基线。

## 使用的 MCP 工具

- `search_kb(query, scope?, include_pending?, expand_synonyms?, limit?, offset?, sort?)`
- `get_entry(id)`
- `propose_entry(draft, credibility, request_id)`
- `propose_update(id, patch, reason, credibility?, request_id)`

这些工具是唯一写入入口。skill 不定义新的写入方式，也不要求 agent 接触文件系统、SQLite、audit 或 review 队列。

## 流程

1. 查重：用 `search_kb(query, expand_synonyms=true, include_pending=true)` 搜症状、错误码、模块、关键日志和同义说法。
2. 命中相似条目时，用 `get_entry(id)` 回读完整结构；如果是在补充或纠错，优先走 `propose_update`，不要新建重复条目。
3. 没有合适条目时，再准备 `propose_entry`。
4. 判定 `entry_type`，只能选：
   - `defect_case`：具体故障/缺陷案例。
   - `triage_rule`：可复用排查规则或判定规则。
   - `code_flow`：代码路径、状态机、调用关系说明。
   - `log_baseline`：日志、指标、错误码的稳定基线。
5. 按 design §3.4 的段落骨架组织正文；允许正文补充额外 heading，但 `section_credibility` 的 key 必须对应骨架段落。
6. 填检索字段：`symptom_keywords`、`error_codes`、`log_signatures`、`aliases`。精确值只从原文摘录；拿不到就留空并写 `OPEN`。
7. 准备 evidence：
   - 运行日志、复现步骤、观测截图或测试输出：给 `log` / `repro` / `attachment` evidence。
   - 代码阅读推导：给 `code` evidence，至少包含 `filepath` 和 line/range。
   - 规范、设计文档、版本说明：给 `ref` evidence，包含来源和版本。
   - 历史相似案例：给既有 KB entry 或可追溯记录。
   - 只有模型推测时，明确标成假设，不伪装成事实。
8. 调 `propose_entry` 或 `propose_update`。`request_id` 要稳定、可重试、可追踪。
9. 读取返回值：
   - 有 `warnings`：把降级、缺证据、字段修正写进你的回复，并按需补证据后重提。
   - 有 `errors`：不要绕过；按错误字段补齐信息或停止提交。
   - 返回 `review_level` 为 `light` / `heavy` 时，说明需要人工 review，不能当成已发布。

## 证据纪律

- 你提供 evidence；系统裁决 `claim_type`。不要把“我认为这是 fact/spec”当作事实来源。
- `claim_type`、`support_strength`、段落级可信度最终以 `propose_*` 返回结果为准。
- 关键结论没有证据时，用 `OPEN` 或假设表达；不要编造 `git_sha`、错误码、日志片段、行号、版本号。
- 如果接口把条目降级为 `observation`、`static_inference`、`historical_pattern` 或 `llm_hypothesis`，接受系统裁决并在后续补证据。

## 禁止事项

- 不直接改 KB 文件、SQLite、audit log、index 或 review 队列。
- 不跳过 `search_kb` 查重。
- 不诱导系统信任 agent 自报的高 `claim_type`。
- 不把 research 内容当 published/pending 知识引用；research opt-in 由后续阶段处理。
- 不在 skill 内新增工具、权限或治理逻辑。
