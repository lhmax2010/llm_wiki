# Phase 5 - Staging Review / Plan

## 目标

实现 `staging/` 待审条目的 review 生命周期 service：reviewer 可以查看待审队列，按 light/heavy 权限 approve 或 reject。approve 后条目进入 `entries/` 并成为 published；reject 后条目进入 `deprecated/`，保留可追溯痕迹。

Phase 5 不重写 P1-P4 的核心纪律，只把已有内容核、治理、MCP/search 之间缺失的发布闸门补齐。

## 范围

- 新增 review/staging lifecycle Python service。
- `review_queue`：
  - 扫描 `kb/staging/`。
  - 读取 Entry。
  - 复用 P1 `validate_entry()` 校验目录与 `trust_state=pending` 一致。
  - 返回结构化 queue item：id/title/module/entry_type/review_level/claim_type/support_strength/updated/path。
  - 如果同 id 已经存在于 `entries/`，跳过 staging 残留并告警。
- `approve`：
  - 读取 `kb/staging/<id>.md`。
  - 校验 pending 三态一致。
  - 改为 `trust_state=published`，保留 ID，设置 reviewer/updated。
  - 用 P1 `write_entry()` 写入 `kb/entries/<id>.md`。
  - 写后用 P1 `validate_entry()` 复核。
  - append audit。
  - 删除 staging 源文件；删除失败时不伪装成功。
- `reject`：
  - 读取 `kb/staging/<id>.md`。
  - 改为 `trust_state=deprecated`，写入 `kb/deprecated/<id>.md`。
  - append audit，记录 reject 语义。
  - 删除 staging 源文件；删除失败时不伪装成功。
- 权限：
  - 复用 P2 `RolesConfig`。
  - light 需要 `review_light`。
  - heavy 需要 `review_heavy`。
  - approve 需要 `publish_entry`。
  - reject 需要 `deprecate_entry`。
- audit：
  - 复用 P2 append-only audit。
  - approve/reject 记录 reviewer、decision、review_level、note、entry_id、target_dir、relative path。
- backlog：
  - 队列数量超过 50 时返回 `backlog_warning=True`。

## 明确不做

- 不做 research promote；`research -> draft` 是 P6。
- 不做 Web review UI；P7/P8 再接。
- 不做 collector draft propose/batch commit；P9 再接。
- 不改 P1 schema/storage/validation 行为。
- 不改 P2 pipeline classify/review_route 行为。
- 不改 P3 MCP propose wrapper。
- 不改 P4 index/search；approve/reject 后的索引刷新留 TODO。
- 不做复杂工作流引擎、动态审批规则、request_changes/needs_clarification。

## 计划步骤

1. 建立 `review/` package 与 `tests/review/`。
2. 定义 `ReviewQueueItem`、`ReviewQueue`、`ReviewOperationResult`。
3. 实现安全路径解析：id 形状校验、resolve、白名单目录 relative_to。
4. 实现 queue：只返回合法 pending staging 条目。
5. 实现 approve：pending -> published，staging -> entries，ID 不变。
6. 实现 reject：pending -> deprecated，staging -> deprecated，ID 不变。
7. 复用 P2 RBAC 和 audit，扩展 audit 可选字段。
8. 补失败测试：坏 id、坏三态、权限不足、target 已存在、audit 失败、source cleanup 失败。
9. 写 dev_memory progress/result 和 review prompt。
10. 跑 R13 三道门并创建 PR。

## 依赖

- Phase 1：`core.models.Entry`、`core.storage.write_entry/read_entry`、`core.validation.validate_entry()`。
- Phase 2：`RolesConfig`、audit append/preflight、review_level 分类结果。
- Phase 3：MCP propose 会把需审内容写到 `staging/`。
- Phase 4：search 读取 `entries/`；approve 后 published 内容会进入 agent 可见路径。

## Baseline

- 分支：`phase/5-staging-review`
- baseline commit：`d740e8629ccff5739a67494eae903f28ce9994a2`
