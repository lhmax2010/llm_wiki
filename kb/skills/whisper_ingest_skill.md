# 经验白话沉淀 Skill（行为契约）

面向接入统一知识库的对话式 agent（Cline / Codex / 其他）。当开发人员用自然语言口述一段技术经验、排查结论或踩坑记录时，你负责把它整理成结构化 KB 候选条目，**先给开发人员确认，再**通过 MCP propose 提交，让 KB 的 P1-P5 治理裁决最终状态。

本 skill 只新增"白话理解 + 原话留底 + 起草后人确认"三个前置环节；**结构化格式、查重、证据驱动、propose 工具全部遵守 `kb/skills/ingest_skill.md`**，不重复定义、不绕过它。冲突时以 ingest_skill 为准。

## 触发场景

- 开发人员说/写一段白话经验，例如："X 模块那个崩溃，我记得是某个初始化顺序的问题，改了之后就好了，具体函数记不清了。"
- 开发人员明确说"帮我把这个记进知识库 / 沉淀一下 / 归档这条经验"。
- **不触发**：开发人员只是闲聊、提问、查已有知识（查知识走 `search_kb`）。

## 流程

### 1. 白话理解 + 结构化起草

- 判 `entry_type`（`defect_case` / `triage_rule` / `code_flow` / `log_baseline`），按 ingest_skill 的定义选。
- 把白话内容拆进 design §3.4 的段落骨架。`section_credibility` 的 key 必须对应骨架段落。
- **白话里拿不到的精确值，留 `OPEN`，绝不编造**——不编 `git_sha` / 行号 / 错误码 / 文件名 / 版本号 / 日志片段。这是铁律：白话经验本来就模糊，宁可留 `OPEN` 也不臆造。
- `claim_type` **默认 `observation`**（人的经验回忆，非强证据）。不自报 `fact`——让 KB 的 `evidence_validate` 裁决。
- 填检索字段（`symptom_keywords` / `error_codes` / `log_signatures` / `aliases`）：只从原话能确认的内容摘录，拿不到留空或 `OPEN`。

### 2. 原话留底（provenance，防曲解）

- 把开发人员的**白话原文**作为来源记录，放进 entry 的 `source_refs`（不是 evidence）：
  ```
  source_refs:
    - type: human_utterance
      role: original_note
      text: "<开发人员的白话原文，原样保留>"
      captured_by: <执行此 skill 的 agent id，如 cline / codex>
      captured_at: "<ISO 时间戳，如 2026-06-22T12:34:56+08:00>"
  ```
- 原话是**出处 / provenance**，不放 evidence——所以不影响 `claim_type` 裁决（已验证：source_refs 不参与裁决）。
- `captured_by` 记录实际执行沉淀的 agent，不要写死；例如 Cline 执行填 `cline`，Codex 执行填 `codex`。
- 目的：结构化内容若有歧义，可回溯原话核对，防 LLM 曲解。
- **原话过长时**（如超过几句话）：不要把长文塞进 frontmatter 的 `text`（会让条目变重）。改为把原话存成附件，`source_refs` 里放 `attachment_id` + `content_hash` 引用；或先存进 research 再引用其 id。短原话直接放 `text` 即可。

### 3. 起草后人确认（确认点 1）★ 必须，不可跳过

- 把起草的结构化草稿**完整展示**给开发人员，包括：
  - 判定的 `entry_type`
  - 各骨架段落填了什么 / 哪些留了 `OPEN`
  - `claim_type`（observation）和理由
  - 原话留底内容
- 明确询问："我把这段经验整理成了上面的条目，原话也留底了。**确认提交到知识库吗？**（可修改 / 可取消）"
- **只有开发人员明确确认，才进入第 4 步 propose。** 要修改 → 改完再确认；取消 → 不提交。
- **绝不在未确认时静默 propose。**

### 4. 按 ingest_skill 规范 propose

- 遵守 `kb/skills/ingest_skill.md` 的完整契约：
  - 先 `search_kb(query, expand_synonyms=true, include_pending=true)` 查重（搜症状 / 错误码 / 模块 / 关键说法 / 同义说法）。
  - 命中相似条目 → `get_entry(id)` 回读 → 若是补充/纠错优先 `propose_update`；否则 `propose_entry`。
  - `request_id` 稳定、可重试、可追踪。
- propose 工具是唯一写入入口；不碰文件系统 / SQLite / audit / review 队列。

### 5. 告知治理结果（两层确认的第二层预告）

- propose 成功后告诉开发人员：
  - "已提交，进 staging，状态 `pending`，`review_level = <light/heavy>`。"
  - "**还需要在 KB 里审核（approve）后才正式发布**。"——两层确认的第二层在 KB review。
- 读返回的 `warnings` / `errors`，**如实转告**：
  - 有 `warnings`（如 `claim_type` 被降级、缺证据）：原样告诉开发人员，不隐瞒治理反馈，并说明可补证据后重提。
  - 有 `errors`：不绕过，按错误字段补齐或停止。

## 证据纪律（继承 ingest_skill）

- 你提供 evidence；系统裁决 `claim_type`。原话留底（source_refs）不是 evidence，不会帮条目撑可信度。
- 白话经验若只有"我记得"而无 log/code/repro 证据，会被系统降级为 `observation` / `llm_hypothesis`——**接受裁决**，如实告诉开发人员"这条目前是观察/假设级，补了证据可升级"。
- 不编造证据来伪装高可信。

## 与 ingest_skill 的关系

- 本 skill = 前置流程（白话理解 + 原话留底 + 人确认）。
- ingest_skill = 录入契约（格式 / 查重 / 证据驱动 / propose 工具 / 治理纪律）。
- 本 skill 不覆盖、不绕过 ingest_skill 的任何治理纪律；冲突以 ingest_skill 为准。

## 禁止事项

- 不编造白话里没有的精确值（行号 / git_sha / 错误码 / 文件名 / 版本 / 日志）→ 留 `OPEN`。
- 不自报高 `claim_type`；接受 KB 降级裁决。
- **不在未经开发人员确认时 propose**（确认点 1 必须）。
- 不把"已 propose"说成"已发布"（还要 KB review，确认点 2）。
- 不把原话塞进 evidence（原话是 provenance，放 `source_refs`）。
- 不直接改 KB 文件 / SQLite / audit / index / review 队列。
- 不诱导系统信任 agent 自报的高可信度。
