# Phase 5 - Staging Review / Plan

## 目标

实现 `staging/` 生命周期 service 和 review 分级流转，让 Phase 2/3 写入的 pending 条目可以由 reviewer 审批后转正到 `entries/`，或被拒绝并留下治理痕迹。

Phase 5 是 P1-P4 之后的发布闸门：它不重新做 schema/evidence/索引/治理 pipeline，而是在已存在的内容核、RBAC、audit、MCP/search 之上补齐人工 review 的 approve/reject 主链路。

## 范围边界

### 本阶段做

- 新建 review/staging lifecycle 模块，提供可测试的 Python service API。
- review queue：
  - 扫描 `kb/staging/` 中 pending 条目。
  - 回读 Entry 后复用 P1 `validate_entry()`，确保目录与 `trust_state=pending` 一致，坏条目不进入可审批队列。
  - 返回 reviewer 需要的结构化队列项：entry id/title/module/entry_type/review_level/claim_type/support_strength/updated 等。
- approve：
  - 读取 `kb/staging/<id>.md`，用系统事实校验路径和三态。
  - 将 Entry 的 `trust_state` 改为 `published`，保留原 ID，设置 reviewer/updated 等审核字段。
  - 用 P1 `core.storage.write_entry()` 写入 `kb/entries/<id>.md`，写前用 P1 `validate_entry(..., entry_path=entries/<id>.md)` 重校验。
  - 写入成功后移除 staging 原文件，避免同一 ID 同时出现在 pending/published。
  - 追加 audit，记录谁审的、什么决定、目标条目、目标路径。
- reject：
  - 提供拒绝决策 API，并记录 audit。
  - 具体物理去向在 restate 时让用户确认：候选是移到 `deprecated/` 并改 `trust_state=deprecated`，或删除 `staging/` 文件但保留 audit。默认倾向前者，因为可追溯且保留 ID。
- 权限：
  - 复用 Phase 2 `RolesConfig` / YAML permission，不重新发明 RBAC。
  - light review 至少要求 `review_light`。
  - heavy review 至少要求 `review_heavy`。
  - approve publish 还应要求 `publish_entry`；reject 若写入 deprecated 则要求 `deprecate_entry`。
  - light/heavy 权限差异在 restate 中明确，请用户确认。
- review 队列堆积阈值：
  - V1 做可测试的 queue stats / backlog warning（>50）接口或字段，不做后台监控服务。
- UT 覆盖 approve/reject 权限、三态校验、原子性、audit、ID 不变、坏 staging 不进队列。

### 本阶段不做

- 不实现 research promote（`research -> draft` 属于 P6）。
- 不实现 Web review UI、review 页面、按钮交互或 HTTP API（P7/P8 再接）。
- 不实现 collector draft propose 或 batch commit（P9）。
- 不改 P1 schema/storage/validation 规则。
- 不改 P2 middleware pipeline 的 classify/review_route 规则。
- 不改 P3 MCP propose wrapper。
- 不改 P4 index/search；approve 后是否触发 rebuild/staleness 只记 TODO，不在 P5 做增量索引。
- 不做复杂工作流引擎、动态审批配置、request_changes/needs_clarification 等 V2 状态。

## 待 restate 明确的口径

- reject 的物理处理：
  - 候选 A：`staging/ -> deprecated/`，改 `trust_state=deprecated`，保留 ID 和条目内容。
  - 候选 B：删除 `staging/` 文件，只保留 audit。
  - 我的倾向：A，更利于追溯和避免“拒绝原因只在 audit 里”的脆弱性。
- approve 的原子性边界：
  - 倾向用“写 entries 临时/原子替换 -> 删除 staging；删除失败告警”的两步策略。
  - 如需强原子跨目录 rename，需要确认是否允许直接文件移动；但用户已提示不要自己拼文件移动，优先用 P1 storage 写入。
- light/heavy 权限差异：
  - 倾向 light：`review_light + publish_entry`。
  - heavy：`review_heavy + publish_entry`。
  - admin `*` 仍放行。

## 计划步骤

1. 等待用户确认 Phase 5 风险档。
2. restate Phase 5 范围、approve/reject 物理流转、权限差异、audit 形态和 DoD，等待用户确认后再编码。
3. 新建 `review/` Python package 与 `tests/review/`。
4. 定义 ReviewDecision / ReviewResult / QueueItem / QueueStats 等 V1 类型。
5. 实现安全 staging 读取：ID 形状校验、路径 resolve/is_relative_to、拒 symlink 逃逸、`validate_entry()` 三态校验。
6. 实现 queue/list/stats：只读 `staging/`，坏条目 warning 后跳过。
7. 实现 approve：权限检查 -> staging 读校验 -> Entry 改 published -> entries 写入校验 -> audit -> staging 清理/回滚告警。
8. 实现 reject：按用户确认的去向执行，保证 audit 和三态一致。
9. 补 UT：权限拒绝、light/heavy、approve 成功、reject 成功、坏 trust_state、路径逃逸、audit 失败处理、staging 清理失败告警、ID 不变。
10. 运行三道门并记录真实输出到 `progress.md`。
11. 创建 review prompt，普通/高风险对应 review 路径按用户确认执行。

## 依赖前置阶段

- Phase 1：`core.models.Entry`、`core.storage.write_entry/read_entry`、`core.validation.validate_entry()`、三态目录一致性。
- Phase 2：`RolesConfig` / permission helper、audit append/build、review_route 分级结果、信任边界修复经验。
- Phase 3：MCP propose 将待审条目写入 `staging/`。
- Phase 4：search 只读 `entries/`，approve 后 published 条目会成为后续 index/search 的正式来源。

## 依赖决策

- 预期不新增 Python 业务依赖。
- 文件写入和 YAML/JSONL audit 继续复用现有标准库 + P1/P2 helper。
- 如实现中发现需要新依赖或改变 Frozen design，按 R8/R1 停下报批。

## Baseline

- 分支：`phase/5-staging-review`
- baseline commit：`d740e8629ccff5739a67494eae903f28ce9994a2`
