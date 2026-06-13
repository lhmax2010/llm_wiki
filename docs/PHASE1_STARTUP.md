# Phase 1 启动话术（给 Codex，单机 SOP 版）

> 把这段发给 Codex，开始统一知识库的 Phase 1 开发。
> 本话术已按团队《外部 AI 开发 SOP》单机版调整（含 restate 闸门、三道门、风险档）。

---

你是统一知识库项目的开发者（Codex），单机开发（本机写代码 + 跑 Python 测试）。
这是一个内网部署、团队共享的知识库：人通过 Web App 读写，agent（如 Kona 缺陷诊断系统）
通过 MCP 读写，**同一份内容核**。

## 开始前必读（R6 上下文加载顺序）
1. 读 `AGENTS.md`（开发常驻铁律）
2. 读 `docs/design.md`（v1.2 FROZEN，总设计基线，全文）
3. 读 `docs/governance.md`（R1-R14 开发规约）
4. 读 `docs/DEV_GUIDE.md`（开发流程：三道门/风险档/验收）
5. design_changes/dev_memory/review 目前为空（首次开发）

## 核心约束（先理解再动手）
- **设计已冻结**：严禁自改 design.md。发现问题走 R1（[DESIGN_ISSUE] + change 提案 + 暂停问我）
- **语言 Python 3.11+**（已冻结，不要自选；类型用 Required/NotRequired）
- **三道门**（单机版）：① 本机静态检查(ruff+mypy)+单测+覆盖率 → ② subagent/checklist 复审 → ③ 集成/端到端验收
- **关键纪律**：证据映射（claim_type 由 evidence 决定）/ research 物理隔离 / 三态目录为主状态边界 / SQLite 发号并发

## Phase 1 前置动作（按顺序，做完才编码）
1. **R10 PR 能力预检**：检查是否 git 仓库/有 remote/指向 GitHub/能创建 PR。不满足输出 [PR_WORKFLOW_ISSUE] 暂停问我。
2. **R12 现有项目扫描**：扫描本仓库已有资产（kb/ 骨架、kb/skills/、config/roles.yaml、目录约定、AGENTS.md），优先复用，不凭空建冲突结构。
3. **R1 启动前设计 Review**：通读 design.md，输出 `docs/review/design_review_phase_1.md`（审覆盖度/模块划分/接口契约/更好方案/阶段拆分/NFR）。发现问题 [DESIGN_ISSUE] 暂停问我。
4. **判风险档报我**（Phase 1 = 内容核+schema+校验，碰证据映射/发号并发 → 倾向高风险，三路 review）。等我确认。

## restate 闸门（前置动作后、编码前）
做完前置 + 我确认风险档后，**先复述**：这个 Phase 做什么、改哪些文件/模块、验收标准（DoD）。
我回"确认，开始"你才编码。不要跳过直接写。

## Phase 1 任务：内容核 + schema + 校验
依赖：无。目标：结构化 entry 的 schema + 纯代码校验 + git/markdown 存储。

范围（design §7 Phase 1 + §4.4 类型）：
- 四类 entry_type schema + 段落骨架
- §4.4 完整类型（Pydantic 实现，注意 Required/NotRequired）
- evidence 强类型校验（纯代码：git ls-files 查 filepath、查附件存在）
- 证据映射规则（claim_type ← evidence，降级/打回，design §4.1.3）
- SQLite 发号（design §4.2.1，含重建：扫 entries 取 max+1，允许空洞）
- 三态物理目录骨架（kb/entries|staging|drafts|research，目录为主状态边界，不一致 E_SCHEMA）

## Phase 1 完成交付（R3，5 项缺一不可）
1. 代码 + UT（行≥80%/分支≥70%/核心≥90%）
2. UT 报告（R13：实际命令 ruff/mypy/pytest --cov + 真实输出摘要）
3. `docs/dev_memory/phase_1_memory.md` + 更新 `docs/dev_memory/INDEX.md`
4. checkpoint tag + 登记 `docs/checkpoints.md`
5. `docs/review/phase_1_review_prompt.md` + GitHub PR

## 第三道门（Phase 1 端到端验收，替代真机 gate）
schema 校验 + 证据映射 + 三态目录 + 发号并发：跑集成测试，实际命令+输出记 dev_memory。

## 可能需要我先给你的
- **hash 口径页**（path_hash/symbol_hash/build_config_id 生成规则）：design 附录 C 标 P1 前补。
  如 Phase 1 的 code_binding 校验需要，先告诉我，我给你 docs/hash_spec.md。

## 现在开始
先做前置动作（R10 预检 → R12 扫描 → R1 设计 Review → 判风险档），把设计 Review 结果 + 风险档给我，
我确认后你 restate，再编码。**不要跳过前置直接写代码。**
