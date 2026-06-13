# 统一知识库 — 全局开发规约（R1–R14）

> 本文档从团队《AI 设计文档生成规范》派生，是统一知识库项目开发的**主干规则**。
> AI Coding 工具（Codex）每次会话开始时必须读取本文档并遵守。
> 配合 docs/design.md（总设计基线，Frozen）使用：design.md 管总设计，本文档管开发纪律。

---

## R1. 设计文档不可变性 + 设计反向 Review

- 开发中**严禁自作主张修改 design.md**。
- **Phase 1 启动前强制设计 Review**：通读 design.md，输出 `docs/review/design_review_phase_1.md`，逐项审查覆盖度/模块划分/接口契约/更好方案/阶段拆分/NFR。发现问题输出 `[DESIGN_ISSUE]`/`[DESIGN_SUGGESTION]` + 建议，暂停等开发者决策。
- **任何阶段发现设计缺陷/矛盾/更好方案**：暂停，输出 `[DESIGN_ISSUE]` + 问题 + ≥1 建议方案，创建 `docs/design_changes/change_{N}.md`（背景/问题/影响范围/备选方案/风险/是否影响 checkpoint/是否返工/待确认问题），等开发者确认。**不得自改设计**。
- 设计变更由**开发者本人**改 design.md 并升版本，AI 不得直接改。

## R2. 决策边界

- **按规划继续不要问**：下一步做什么（DAG 已定）/ 要不要开始 Phase N（DoD 满足即开始）/ 变量命名/函数位置/测试补充/内部结构（自行决策）。只有一个合理方案就直接做。
- **必须暂停询问**：出现 ≥2 实现方案 / 引入升级替换第三方依赖 / 改公共 API 或跨阶段接口契约 / 改数据模型 Schema / 调安全模型 / 性能预算取舍 / 部署运行环境变更 / 兼容性向后兼容 / 回滚策略 / 大范围重构（R11）/ 设计与需求矛盾（R1）。

## R3. 每阶段交付物（缺一不可，5 项）

1. **代码**：实现 + UT + 必要集成测试。不引入无关 diff、不升级无关依赖、不引入 secret/token。
2. **UT 报告**：通过/失败数；行覆盖率 ≥80%、分支 ≥70%（关键模块 ≥90%）；覆盖率报告路径；Coverage 例外说明（generated/纯类型/glue/启动代码可豁免，核心业务逻辑不得豁免）。
3. **dev_memory.md**（`docs/dev_memory/phase_{N}_memory.md`）：实现思路与关键决策（为什么）/ 走过的弯路与放弃方案 / 与设计偏差（须经 R1）/ 遗留 TODO。要求陌生 AI 10 分钟恢复上下文。
4. **checkpoint**：git tag `checkpoint/phase_{N}_{shortdesc}` 指向通过 UT 的 commit；在 `docs/checkpoints.md` 登记 tag/hash/范围/回退指令/回退后状态描述。
5. **Review Prompt**（`docs/review/phase_{N}_review_prompt.md`）：变更文件清单 / design 章节链接 / UT 结果与覆盖率（含 R13 命令输出）/ GitHub PR 链接 / 重点审查项 / 未覆盖场景 / Coverage 例外。Review AI 职责：审代码质量+UT+符合设计、审设计本身、每条反馈带严重等级（BLOCKER/MAJOR/MINOR/NIT）+ 类型标签（CODE_ISSUE/DESIGN_SUGGESTION/ALTERNATIVE）、不得自改代码或设计。结果存 `phase_{N}_review_result.md`。

## R4. Subagent 隔离协议

与当前阶段无关的新需求/想法：不 compact 进主上下文、不中断当前阶段、启动 subagent 在独立分支处理、结果写 `docs/spinoffs/{topic}.md`。主 agent 继续按设计推进。

## R5. 检查点回滚

开发者说"回到 checkpoint X"：立即 `git reset --hard checkpoint/phase_X_*`，读该阶段 dev_memory 恢复上下文，确认后继续。

## R6. 上下文加载顺序（每次会话开始执行）

1. 读 design.md 全文 → 2. 读 design_changes/（已批准变更）→ 3. 读 dev_memory/（已完成阶段）→ 4. 读 checkpoints.md（当前阶段）→ 5. 读 review/*_review_result.md（上轮闭环+TODO）→ 6. 读 spinoffs/ → 7. 开始任务。

## R7. 非功能性约束

- 日志：关键路径结构化日志（trace_id/level/业务字段），严禁打印密钥/Token/PII。
- 错误处理：外部调用必须超时+重试+降级。
- 安全：密钥走环境变量/Secret Manager 严禁硬编码；用户输入校验（注入/路径穿越/XSS）。
- 性能：标注关键路径预算（如 P95<200ms），UT 加基准。
- 可观测：关键指标埋点（成功率/延迟/错误码分布）。

## R8. 依赖管理

锁定版本（poetry.lock 等，本项目 Python），不随手升级。引入/升级/降级/替换依赖必须经 R2 询问。

## R9. Git 与 PR 规范

- 分支：`phase/{N}-{short-desc}`
- Commit：`[Phase N] <type>: <subject>`（conventional commits）
- 一阶段一 PR，PR 描述链接 design.md 对应章节。

## R10. Phase 1 仓库与 PR 能力预检（强制）

Phase 1 编码前检查：是否 git 仓库/有 remote/remote 指向 GitHub/具备 branch+commit+push+PR 能力/能按分支规范创建/能按 `[Phase N]` 格式创建 PR。GitHub PR 是默认强约束，不得自行降级。无法满足则输出 `[PR_WORKFLOW_ISSUE]` + 问题 + 仓库状态 + 对 Review 影响 + 可选方案，暂停等开发者决定。

## R11. 大范围重构控制

每 Phase 只改与当前阶段直接相关文件。禁止顺手重构/升级/重命名/清理。必须大范围重构（≥3 模块或公共接口）则暂停输出 `[REFACTOR_PROPOSAL]`（为什么/风险/范围/影响/替代方案/推荐）。与当前 Phase 无关的重构拆独立 Phase 或写 spinoffs/。

## R12. 现有项目优先原则

开发前扫描现有仓库：README/docs、build 脚本与包管理（pyproject.toml）、测试框架、lint/format 配置、CI 配置、模块边界、日志/配置/错误处理方式、代码风格。新代码优先复用现有结构/工具链/框架。不得凭空创建冲突的新目录/框架/构建方式。design.md 与现有项目冲突则输出 `[DESIGN_ISSUE]` 按 R1 暂停。

> 本项目说明：复用了 KB v5 + LLM Wiki v10 的设计思路（见 design.md 附录 A 溯源），Phase 1 前应扫描本仓库已有资产（kb/ 目录骨架、skills/、schema 定义）。

## R13. 测试真实性与命令记录

每 Phase 记录**实际执行过**的命令（非声称）：build/lint/format check/type check/UT/coverage/integration。不得声称"测试通过"而不提供输出摘要。每条命令附：实际命令字符串 + 输出摘要（关键行）+ 通过/失败状态。无法运行则说明原因/缺失环境/替代验证/需开发者本地执行的命令。结果同时写 dev_memory 和 review_prompt。

## R14. Review 闭环规则

Review AI 反馈必须闭环：BLOCKER 必修复才合并；MAJOR 原则必修，不修需开发者在 review_result.md 显式确认放行；MINOR 记 dev_memory TODO；NIT 可选。修复后更新代码+测试+dev_memory+review_result（每条反馈处理结果：已修复/已放行/转 TODO/拒绝）。DESIGN_SUGGESTION/ALTERNATIVE 必须走 R1 设计变更提案，不得直接改设计或自行返工。

---

*本规约从团队设计规范派生，与 design.md 并存。开发期间严格遵守。*
