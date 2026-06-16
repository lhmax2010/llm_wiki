# Phase 5 - Staging Review / Progress

## 风险档

- 判定：高风险，三路 review（Claude + ChatGPT + Kimi）。
- 理由：Phase 5 是 `staging/` 内容进入 `entries/` 的发布闸门；一旦错误发布，内容会立即暴露给 P3 MCP 和 P4 search 的 agent 读路径。
- 专项必查：
  - approve/reject 是否绕过 P1 三态目录纪律。
  - 权限是否完全复用 P2 RBAC，不信调用方自报。
  - audit 失败、源文件删除失败是否会伪装成功。

## 关键决策

- 审批 service 独立成 `review/` Python package。
  - 原因：P5 先交付核心流转，不提前做 Web/API UI；后续 HTTP/Web 可以直接调用这个 service。
  - 排除方案：把审批做成 P2 middleware。原因是 design 已说明 staging 生命周期是独立 service，不属于 middleware pipeline。

- `review_level` 由系统事实决定，不由调用方自报。
  - P2 audit record 扩展记录 `review_level`；P5 queue/approve/reject 从 audit 读取该 level。
  - 老 audit 或缺失 level 的 staging 条目保守按 `heavy` 审。
  - 原因：延续 P2 R14 的信任边界原则，不能让调用方把 heavy 自报成 light。

- reject 去 `deprecated/`，不删除。
  - reject 时将 `trust_state=pending` 改为 `deprecated`，写到 `kb/deprecated/<id>.md`，ID 不变。
  - “被拒绝”与“曾发布后废弃”的语义区别不污染 schema，而是写入 audit：`operation=review_reject`、`decision=reject`、`review_level`、`reviewer`、`note`。

- approve/reject 都更新 `updated`。
  - `created` 和 `id` 保持不变。
  - `updated` 表示审核流转/发布时刻，方便后续 human UI 和 audit 对齐。

- 跨目录流转采用保守顺序，不宣称事务原子。
  - approve：读 staging 并校验 pending -> 改 `trust_state=published` -> P1 `write_entry()` 原子写 entries -> P1 `validate_entry()` 复核 -> append audit -> 删除 staging 源文件。
  - reject：同理写 deprecated，`trust_state=deprecated`。
  - audit append 失败：回滚新写目标文件，保留 staging 源文件，返回失败。
  - 源文件删除失败：不回滚已审计目标，返回失败并记录 error log；最坏状态是可检测的重复，而不是状态错乱或静默成功。

- 并发窗口处理。
  - `review_queue` 扫到 staging 残留时，如果同 id 已经存在于 `entries/`，跳过并告警。
  - approve/reject 发现目标已存在时返回 `E_DUP`，不覆盖。
  - TODO：后续如出现多 reviewer 并发，需要引入文件锁或 SQLite review state 表做 CAS。

- 路径和三态防护。
  - 所有按 id 读 staging/entries/deprecated 的入口先校验 `^KB-\d{4}-\d{4}$`。
  - 读取前 `resolve(strict=True)`，并确认 resolved path 在白名单目录内。
  - 读取和写目标后都调用 P1 `validate_entry(..., kb_root=..., entry_path=...)`，目录与 `trust_state` 不一致直接跳过/失败。

- 权限复用 P2 RBAC。
  - `light` 审批要求 `review_light` + action permission。
  - `heavy` 审批要求 `review_heavy` + action permission。
  - approve action permission 是 `publish_entry`；reject action permission 是 `deprecate_entry`。
  - 通过 `RolesConfig.permissions_for_user()` 解析 user -> role/permissions，不信调用方 role。

## 已完成改动

- 新增 `review/` package：
  - `review/service.py`：queue、approve、reject、audit、路径防护、权限检查。
  - `review/__init__.py`：导出 Phase 5 service API。
- 扩展 P2 audit record：
  - `governed_api.types.AuditRecord` 增加可选 `review_level`、`decision`、`reviewer`、`note`。
  - `build_audit_record()` 在 middleware context 有 `review_level` 时写入 audit。
- 新增 `tests/review/test_service.py`：
  - queue 读取、review_level 来源、backlog warning。
  - approve 发布到 entries，ID 不变，trust_state 改 published，updated/reviewer 更新。
  - reject 到 deprecated，audit 保留 reject 语义。
  - light/heavy 权限差异。
  - 坏 id、坏三态、目标已存在、audit 失败、源文件删除失败。
- 更新 `pyproject.toml`：coverage 纳入 `review` package。

## TODO

- 多 reviewer 并发审批时，后续可以加文件锁或 SQLite review state CAS，避免目标存在检查和写入之间的竞态。
- approve/reject 后索引不会自动增量刷新；P4 当前仍依赖 rebuild/fallback，后续可在 review service 成功后触发 index invalidation/rebuild hook。
- `deprecated/` 中 reject 与 published 后 deprecate 当前靠 audit 区分；如果 Web UI 需要直接筛选，可后续增加只读索引视图，不改 Entry schema。
