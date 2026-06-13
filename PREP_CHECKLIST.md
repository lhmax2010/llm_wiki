# 开发前准备清单（你按这个执行）

> 按团队《外部 AI 开发 SOP》单机版。打勾执行，全部完成就能让 Codex 开始 Phase 1。

## A. 环境（一次性）
- [ ] git 能用：`git --version`
- [ ] Python 3.11+：`python --version`（design §4.4 用 Required/NotRequired 需 3.11+）
- [ ] Codex 能用：`codex --version`
- [ ] gh（要 Codex 自动提 PR，可选）：`gh --version`
- [ ] Node（前端 P7+ 才需要，后端阶段可后装）：`node -v`

## B. 仓库就位（一次性）
- [ ] 解压本包，进 unified-kb/
- [ ] `git init && git add . && git commit -m "init unified-kb v1.2"`
- [ ] 连官方 GitHub：`git remote add origin <url> && git push -u origin main`
- [ ] 确认 docs/design.md 状态是 Frozen（已是）

## C. P1 前置（开发前）
- [ ] **hash 口径页**：找 Claude 要 `docs/hash_spec.md`（path/symbol/build_config hash 生成规则）
      —— 这是 P1 唯一硬前置（design 附录 C）
- [ ] config/roles.yaml 填实际人员标识（可选，开发中填也行；填了别外发）

## D. 不阻塞、开发中补
- [ ] severity 实际分级（字段已透传，定了告诉 Claude 补"常见值参考"）
- [ ] 种子知识 20-30 条 + 同义词初始组（破冷启动，P5/P6 后录）

## E. 启动 Phase 1
- [ ] 把 `docs/PHASE1_STARTUP.md` 那段发给 Codex
- [ ] Codex 做前置（R10 预检→R12 扫描→R1 设计 Review→判风险档）
- [ ] 你确认风险档 + Codex restate → 回"确认，开始"
- [ ] 之后每个 Phase 按 `docs/DEV_GUIDE.md` 的循环走

## 关键文件位置
| 文件 | 作用 |
|------|------|
| docs/design.md | 总设计（Frozen，Codex 不得改）|
| docs/governance.md | R1-R14 开发规约 |
| docs/DEV_GUIDE.md | 开发流程执行 guide（你看这个）|
| docs/PHASE1_STARTUP.md | 发给 Codex 的启动话术 |
| AGENTS.md | Codex 常驻铁律（自动读）|
| docs/test-guides/ | 端到端验收清单 |
| config/roles.yaml | RBAC 角色（填实际人员）|

## 你在整个开发中真正动手的
确认风险档 → Codex restate 后回确认 → 看 PR → 转三方 AI review → 拍板放行。其余 Codex 做。
