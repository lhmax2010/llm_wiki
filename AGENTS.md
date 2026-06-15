# AGENTS.md — 统一知识库项目的 AI 开发常驻规则

> Codex/Claude Code 每次会话自动读取本文件。这是开发铁律，配合 docs/governance.md（R1-R14）与 docs/design.md（Frozen 设计）。

## 0. 优先级
平台/系统/developer 指令 > 当前用户明确指令 > 本文件与 governance.md > 个人推断。
本 SOP 是执行协议不是自动化引擎：工具/权限/环境不支持某步时，**停下报告降级方案，不假装完成**。

## 1. 设计不可变（R1）
- 严禁自改 docs/design.md（Frozen）。发现设计缺陷/矛盾/更好方案 → 暂停，输出 [DESIGN_ISSUE] + ≥1 方案，建 docs/design_changes/change_N.md，等开发者确认。设计由开发者本人改。

## 2. 决策边界（R2）
- 按 DAG 推进不要问"下一步做什么"。实现细节（命名/文件位置/内部结构）自行决策。
- 必须暂停问：≥2 实现方案 / 引入升级依赖 / 改公共 API 或跨阶段接口 / 改数据模型 Schema / 调安全模型 / 性能取舍 / 部署变更 / 大范围重构 / 设计与需求矛盾。

## 3. 每 Phase 交付物 + dev_memory 三件套（R3，缺一不可）
- 代码+UT / UT报告(覆盖率行≥80%分支≥70%核心≥90%) / checkpoint(高风险打tag,低风险记hash) / docs/review/phase_N_review_prompt.md + PR
- **dev_memory 三件套**（每个 Phase 一个文件夹 `docs/dev_memory/phase_<N>_<名称>/`）：
  - `plan.md`：开 Phase 时写——目标/范围边界(明确做什么不做什么)/计划步骤/依赖前置
  - `progress.md`：**开发中持续追加**——关键决策/排除的方案/为什么/进度日志。不等收尾（防事后编造）
  - `result.md`：收尾写——最终状态/测试覆盖率/PR链接/commit/遗留TODO/下一步
  - 并更新 `docs/dev_memory/INDEX.md`（phase 总索引）
- 假设接手的是完全陌生的 AI/工程师，10 分钟能恢复上下文。dev_memory 与代码/git 状态必须一致，不一致立即停下报告。

## 4. 本项目技术约束
- 后端 **Python 3.11+**（已冻结，design §2.1，不得自选语言）；类型用 Required/NotRequired（design §4.4）。
- 前端 React（P7+）。存储 Git+Markdown+YAML（SSOT）+ SQLite（索引+发号）。
- 依赖锁版本（poetry.lock）；引入/升级依赖必须按 R2 问（R8）。
- 静态检查：ruff format + ruff check + mypy（必跑）；前端 eslint。
- 测试真实性（R13）：必须贴实际命令+输出，不许只声称通过。

## 5. 三道门（适配单机版）
① 本机静态检查+单测+覆盖率 → ② subagent/checklist 复审 → ③ 集成/端到端验收（merge 前 gate，没过不许 merge）。
> 本项目无 GBS 交叉编译/真机；第三道门是集成/端到端验收（见 docs/DEV_GUIDE.md 步骤 D）。

## 6. 关键纪律（本项目特有，碰到必格外小心）
- **证据映射**：claim_type 由 evidence 决定，不是 agent 凭空声明（design §4.1.3）。evidence_validate middleware 必须 100% 运行时强校验（type=code 必须有 filepath 等）。
- **research 物理隔离**：agent 主搜索索引物理不含 research；research 不能当正式 evidence；agent 不能 create/update research。这是安全边界，P6 实现时严格守。
- **三态目录为主状态边界**：目录与 trust_state 字段不一致时校验失败（E_SCHEMA），不是 warning。
- **ID 并发**：SQLite 发号保唯一，允许空洞，唯一性优先于连续性。

## 7. Git/PR（R9/R10）
- 分支 phase/<N>-<slug>；commit `[Phase N] <type>: <subject>`；一 Phase 一 PR，PR 描述链接 design 章节。
- Phase 1 前做 PR 能力预检（R10），不满足输出 [PR_WORKFLOW_ISSUE] 暂停。
- destructive git（reset --hard/force-push）执行前 git status 检查 + 开发者授权；有未提交改动只报告不自行 stash/reset/clean。

## 8. Subagent 隔离（R4）
与当前 Phase 无关的新需求/想法：不打断当前 Phase，启 subagent 独立分支处理，结果写 docs/spinoffs/{topic}.md。

## 9. Review 闭环（R14）
BLOCKER 必修才合并；MAJOR 原则必修，不修需开发者显式放行；MINOR 记 dev_memory TODO；NIT 可选。设计类意见走 R1 不直接改 design。

## 9b. 收尾顺序（硬约束，不可跳）
dev_memory 是仓库内文件，必须随 PR 分支一起提交，不能 merge 后才写。固定顺序：
1. 前提：端到端验收过 + review 闭环
2. 写 result.md + 更新 INDEX.md
3. **先 commit/push 进 PR 分支**（`git add docs/dev_memory/<phase>/result.md docs/dev_memory/INDEX.md`）
4. 再 merge（有权限+CI过；否则报告阻塞不强合）
5. 打 checkpoint：先切主分支最终 commit 再打 tag（高风险 tag message 含 PR号+验收摘要；低风险只记 commit hash）

## 10. 失败 3 次刹车
同一问题连续修 3 次不过 → 停，输出刹车报告（试过的 3 种方案+各自报错 / 根因猜测 / 需开发者决策的点），等介入，不堆补丁。

## 11. 外发过滤
转三方 AI 前，diff/PR描述/日志/dev_memory 过滤 secret/token/内部路径/真实人员标识（config/roles.yaml 真实人员不外发）。
