# 统一知识库 — Codex 开发执行 Guide（单机版）

> 给你（开发者）按步骤执行。基于团队《外部 AI 开发 SOP》适配——
> 原 SOP 是 Tizen GBS 双机版（Windows 写代码 + Linux 跑 GBS 交叉编译/sdb 真机）。
> **本项目是 Python + React Web 应用，没有 GBS 交叉编译、没有 sdb 真机**，所以：
> - ✅ 保留：流程骨架（开 Phase→风险档→restate→三道门→PR→三方 review→R14 闭环→拍板→checkpoint）
> - 🔧 适配：把"Linux 机 GBS 编译 + 真机验证"那道门，换成本机的 **pytest + 覆盖率 + 集成测试**
> - ❌ 去掉：双机交接（§B）、GBS、sdb、交叉编译相关——本项目用不上
>
> 单机即可：一台机跑 Codex 写代码 + 跑 Python/前端测试。

---

## 这份 Guide 怎么用

整个开发是「每个 Phase 一个循环」，共 12 个 Phase（design.md §7 DAG）。
你真正动手的就几处：**确认风险档、看 PR、转三方 AI review、拍板放行**。其余 Codex 做。

下面分「一次性准备」+「每个 Phase 的循环」。

---

## 一、一次性准备（开发前做一次）

### 步骤 0：环境预检
确认这些能出版本（缺的先装）：
```
git --version          # git
python --version       # Python 3.11+（design 用了 Required/NotRequired，需 3.11+）
node -v                # Node（前端 P7+ 才需要，后端阶段可后装）
codex --version        # Codex
gh --version           # GitHub CLI（要 Codex 自动提 PR，可选）
```

### 步骤 1：仓库就位
本包（unified-kb/）解压后就是仓库骨架，已含：
- `docs/design.md`（v1.2 FROZEN）
- `docs/governance.md`（R1-R14）
- `docs/PHASE1_STARTUP.md`（Codex 启动话术）
- 模块目录骨架 + kb/ 运行时目录 + config/roles.yaml + skills/

初始化 git + 连官方 GitHub（R10 要求 PR 能力）：
```bash
cd unified-kb
git init
git add .
git commit -m "init unified-kb from design v1.2 FROZEN"
git remote add origin <你的 GitHub repo url>
git push -u origin main
```

### 步骤 2：补 P1 前置（design 附录 C）
P1 启动前必须补一项：
- **hash 口径页**：path_hash/symbol_hash/build_config_id 怎么生成。
  → 这个我（Claude）可以帮你写，开发前告诉我，我给你一页放进 `docs/hash_spec.md`。
  （其余 severity 分级/种子知识/同义词不阻塞 P1，开发中随时补。）

### 步骤 3：确认 design Frozen
`docs/design.md` 开头状态是 **Frozen** ✓（已是）。Codex 不得改它，改设计走 R1 流程。

---

## 二、每个 Phase 的循环（12 个 Phase 重复这套）

> Phase 顺序见 design.md §7 DAG。关键路径 P1→P2→P3→P5→P6→P8→P9。
> P1-P5 + P10a 完成后，Kona 就能接入主链路（不必等 Web）。

### 步骤 A：开 Phase + 你确认风险档
对 Codex 说（首个 Phase 用 PHASE1_STARTUP.md，之后用这句）：
```
读 docs/design.md（§7 开发阶段拆分 DAG）和 docs/dev_memory/ 已完成阶段，
开始下一个 Phase。按 docs/governance.md 做开 Phase 准备：
定位下一个 Phase、开分支 phase/<N>-<描述>、记 baseline commit、
判风险档报我，等我确认。
```

Codex 会判这个 Phase 的风险档，你确认。

> 🟢 **dev_memory 三件套（每个 Phase 一个文件夹，SOP 要求）**：开 Phase 时 Codex 在 `docs/dev_memory/phase_<N>_<名称>/` 建：
> - `plan.md`（开 Phase 时写：目标/范围边界/计划步骤/依赖前置）
> - `progress.md`（**开发中持续追加**：关键决策/排除的方案/进度——不等收尾，防事后编造）
> - `result.md`（收尾时写：最终状态/测试覆盖率/PR/遗留 TODO/下一步）
> 并更新 `docs/dev_memory/INDEX.md`（phase 总索引）。

**本项目风险档对照**（适配版）：

| 改动碰到什么 | 风险档 | 复审 | 三方 review |
|---|---|---|---|
| 治理 middleware / 证据映射 / research 物理隔离 / 权限 / 并发发号 | 高 | 做 | 三路（Claude+ChatGPT+Kimi）|
| 一般功能 / MCP 工具 / 索引 / Web 组件 | 普通 | 做 | 两路（Claude+ChatGPT）|
| 小修 / 单测 / <200 行 | 低 | 跳过 | 一路（Claude）|

> 哪些 Phase 偏高风险（建议三路 review）：**P2（治理 pipeline）、P6（research 隔离）、P10b（Kona 接入）**。
> 这几个碰可信度纪律/安全边界，错了影响全局。

### 步骤 B：确认 Codex 复述理解（restate 闸门）
Codex 复述：这个 Phase 做什么、改哪些文件、验收标准（DoD）。
对了回"确认，开始"。不对就纠正。**别跳过这步**——restate 能挡掉它理解跑偏。

### 步骤 C：实现 + 三道门（适配版，全在本机）

🤖 Codex 做：
1. **实现代码** + 单测；关键决策当下写进 dev_memory（防事后编造）。
2. **第一道门·静态检查 + 测试（本机，替代原 SOP 的"Linux GBS 编译"）**：
   ```bash
   # 格式 + lint（Python）
   ruff format .          # 或 black
   ruff check .           # lint
   mypy core/ governed-api/ ...   # 类型检查（design §4.4 是 typed，必跑）
   # 单测 + 覆盖率
   pytest --cov --cov-report=term-missing
   ```
   - 覆盖率：touched files 行≥80%/分支≥70%（核心≥90%，governance R3）
   - 前端 Phase（P7+）：`npm run lint && npm test`（vitest/jest）
3. **第二道门·复审**：subagent 复审 或 checklist 复审（普通档+做；低风险跳过）。

> 🔧 **适配说明**：原 SOP 第三道门是"Linux 机 GBS 编译 + sdb 真机"。本项目没有这些，
> **第三道门替换为「集成测试 + 端到端验收」**——见步骤 D。

### 步骤 D：第三道门·集成/端到端验收（替代原"真机 gate"）
按 Phase 性质，本机跑对应验收（这是 merge 前 gate，没过不许 merge）：

| Phase | 端到端验收（替代真机）|
|---|---|
| P1-P2 | schema 校验 + 证据映射 + 三态目录 + 发号并发：跑集成测试 |
| P3 | MCP 工具端到端：起 MCP server，6 工具实际调通 |
| P4 | 检索：grep+同义词+CJK 实际命中测试 |
| P5 | staging→review→published 全流程跑通 |
| P6 | **research 隔离验收（关键）**：验证 agent 主搜索物理搜不到 research、不能当 evidence、agent 不能 create |
| P7/P8 | Web：起前端，人读视图隐藏字段、编辑分级、图谱渲染 |
| P9 | collector：拖入样例 PDF→batch preview→人确认→draft 入库 |
| P10b | **Kona 接入验收**：Kona 端到端接 MCP、证据映射提交、research opt-in 独立通道 |

Codex 跑完把**实际命令 + 输出**按 R13 记进 dev_memory。

> 💡 R13 在单机版简单了：你和 Codex 在同一台机，它能直接跑测试、直接拿到真实输出，
> 不需要双机"回贴"。但 R13 铁律不变：**必须贴真实命令+输出，不许只声称通过**。

### 步骤 E：提 PR → 人工 review（你看 + 转三方 AI）
Codex 提 PR（有 gh 用 `gh pr create`；没有则 push 后你在 GitHub 网页建）。

**外发前硬检查**：转三方 AI 前，确认 diff/PR描述/测试日志/dev_memory 不含 secret/token/内部路径/真实人员标识（config/roles.yaml 里如果填了真实人员，别外发那部分）。

你把代码（脱敏后）转三方 AI（按风险档定几路）：
- **Claude**：`独立 review 找 bug，重点证据映射正确性/research 隔离/并发/权限边界，逐条标严重程度。[贴diff]`
- **ChatGPT**（普通档+）：同上 + `Claude 已审发现：<finding>，请确认/反驳并补充。`
- **Kimi**（仅高风险，如 P2/P6/P10b）：同上 + 贴前两路 finding。

按 R14 闭环：BLOCKER/MAJOR 必修 → Codex 修 → 你复验 → 更新 PR → 你复确认。

### 步骤 F：拍板放行（顺序别错，硬约束）
你回"通过，可以 merge"后，Codex 按**固定顺序**收尾（dev_memory 是仓库内文件，必须随 PR 分支一起提交，不能 merge 后才写——否则游离在 PR 外、丢留痕）：
1. 前提：端到端验收过、review 闭环。
2. 写 `result.md`（验收结果/遗留 TODO/决策小结）+ 更新 `INDEX.md`。
3. **先提交进 PR 分支再 merge**：
   ```bash
   git status --short   # 确认只有 dev_memory 相关改动
   git add docs/dev_memory/<phase>/result.md docs/dev_memory/INDEX.md
   git commit -m "[Phase N] docs: dev_memory result"
   git push
   ```
4. 然后 merge（有权限 + CI 过；否则报告阻塞不强合）。
5. 打 checkpoint tag——**先切主分支最终 commit 再打**（避免停在 PR 分支打错）：
   ```bash
   git fetch origin && git switch main && git pull --ff-only
   git tag -a checkpoint/phase_N_<desc> -m "<PR号 + 验收摘要>"
   git push origin checkpoint/phase_N_<desc>   # 避免 tag 只留本地
   ```
   - **高风险 phase**：打 tag 在 merge 后主分支最终 commit，message 必须含 PR 号 + 验收摘要。
   - **低风险 phase**：不打 tag，只在 `docs/checkpoints.md` 记 merge 后主分支 commit hash。
   - 统一在主 git 流程打，push 到远端。

---

## 三、核心铁律（适配版速查）

1. **单机**：一台机 Codex 写代码 + 跑 Python/前端测试。无双机交接。
2. **三道门**：① 本机静态检查+单测+覆盖率 → ② subagent/checklist 复审 → ③ 集成/端到端验收（merge 前 gate）。
3. **R13 证据**：Codex 直接跑测试拿真实输出记 dev_memory，不许只声称通过。
4. **人工 review = 你 + 三方 AI**（PR 后），按风险档定几路。
5. **R14 闭环**：BLOCKER/MAJOR 必修，设计类意见走 R1 变更提案不直接改 design。
6. **外发硬检查**：转三方 AI 前过滤 secret/内部路径/真实人员标识。
7. **destructive git 要你授权**；**端到端验收是最终 gate**；**同一问题失败 3 次刹车**。
8. **优先级**：平台/系统/developer 指令 > 你的明确指令 > 本 Guide 与 governance.md。

---

## 四、和原双机 SOP 的差异（备查）

| 原双机 SOP | 本项目（单机适配）|
|---|---|
| Windows 写 + Linux 机 GBS 编译/sdb 真机 | 单机：Codex 写 + 本机 pytest |
| §B 双机交接（git/rsync/scp 传代码到 Linux）| 无（同一台机）|
| 第三道门 = GBS 编译 + 真机 gate | 第三道门 = 集成/端到端验收 |
| R13 证据靠你从 Linux 机回贴 | Codex 直接跑直接记（同机）|
| clang-format/clang-tidy（C/C++）| ruff/black/mypy（Python）+ eslint（前端）|
| 真机为唯一最终验收 | 端到端验收为最终 gate |
| 失败 3 次刹车 / 风险档 / R14 | **不变，照搬** |

流程骨架完全一致，只是把"Linux 原生编译/真机"换成"本机 Python/前端验证"。
