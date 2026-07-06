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

- 多 reviewer 并发已用 per-entry lock 收紧；硬崩/断电时 `kb/indexes/review_locks/<id>.lock` 可能残留，导致该 id 后续 review 持续 `E_DUP`，可手动删除对应 `.lock` 恢复；后续可升级到锁超时/PID 检查或 SQLite review state CAS。
- crash recovery：如果 target 已写入且 audit/cleanup 中途 crash，后续需要维护脚本扫描“entries/deprecated 有终态但 audit 缺 review_approve/review_reject”的异常。
- approve/reject 后索引不会自动增量刷新；P4 当前仍依赖 rebuild/fallback，后续可在 review service 成功后触发 index invalidation/rebuild hook。
- `deprecated/` 中 reject 与 published 后 deprecate 当前靠 audit 区分；如果 Web UI 需要直接筛选，可后续增加只读索引视图，不改 Entry schema。

## R14 Review Closure

- 根因总纲：Phase 5 是发布闸门，必须同时保证“终态唯一性”和“目录边界”。一个 entry id 只能处于一个终态（`entries/` 或 `deprecated/`），任何状态目录 resolve 后都必须仍在 `kb_root` 内，不能让 symlink 把发布/废弃路径带出 KB。

- FIX-1 [BLOCKER] 终态互斥破坏。
  - 修复：transition 前同时检查 `entries/<id>.md` 和 `deprecated/<id>.md`，任一存在即 `E_DUP`。
  - 修复：queue 也把任一终态存在视为 staging residue，跳过并 warning。
  - 修复：新增 per-entry lock，使用 `kb/indexes/review_locks/<id>.lock` + `O_CREAT|O_EXCL` 原子认领；锁内再次检查终态，堵住并发 TOCTOU。
  - 测试：`test_review_queue_skips_when_any_terminal_state_exists`、`test_review_refuses_transition_when_any_terminal_state_exists`、`test_review_lock_blocks_concurrent_transition`。

- FIX-2 [BLOCKER] 状态目录 symlink 逃逸。
  - 修复：`_source_root()` 现在先 resolve `kb_root`，拒绝三态目录自身是 symlink，并确认 resolved source root `is_relative_to(kb_root)`。
  - 测试：`test_state_directory_symlink_is_rejected`、`test_terminal_directory_symlink_is_rejected`。

- FIX-3 [MAJOR] reject 无法处置失效条目。
  - 修复：queue 使用 `validate_entry(..., check_evidence_exists=False)`，让 stale evidence 条目仍能进入待审队列。
  - 修复：reject 路径只要求 Entry 可读、id 与文件名一致、`trust_state=pending`、路径位于 staging；不跑完整 schema/evidence 校验。approve 仍保持完整 validation。
  - 测试：`test_review_queue_includes_entry_with_stale_code_evidence`、`test_reject_can_dispose_entry_with_stale_code_evidence`、`test_reject_can_dispose_entry_with_invalid_body`。

- FIX-4 [MINOR] 源清理失败语义。
  - 修复：audit 已成功且 target 已写入时，source cleanup 失败返回 `ok=True` 并带 `warning.field=staging_residue`，同时写 error log；不再用 `ok=False` 误导上游重试造成重复操作。
  - 测试：`test_source_cleanup_failure_is_reported_after_audited_publish`。

- FIX-5 [MINOR] id regex。
  - 修复：`_valid_entry_id()` 从 `match()` 改为 `fullmatch()`。
  - 测试：`test_entry_id_validation_uses_fullmatch`。

- TODO：`review_level` 权威源当前来自可变 audit 日志，内网信任模型下暂不阻塞，但它既可篡改也不适合作为长期高性能查询源。后续应通过 R1 设计变更，把 review routing metadata 持久化到受校验的 frontmatter 或独立 SQLite review state 表。

## 2026-07-06 - PR #12 P5 Reject Update Proposal Fix

- Root cause: P8 added approve republish for update proposals, but the symmetric reject path still used the net-new reject semantics. An update proposal already has `entries/{id}.md`, so reject hit the terminal-entry guard and surfaced as "review entry is not available" through Web review. The reported `log_baseline` type was incidental; the bug affected any `propose_update` rejection.
- Fix: reuse the existing audit-derived `_is_update_proposal()` classification. For `decision=reject` + `operation=propose_update`, allow the existing published entry during terminal checks, load the published entry for the response, append audit with `operation=review_reject_update`, then delete only the staging proposal. The branch does not write `deprecated/` and does not modify `entries/{id}.md`.
- Safety invariants retained: net-new reject still writes to `deprecated/`; deprecated same-id still returns `E_DUP`; per-entry lock, symlink/path checks, id validation, RBAC, and audit preflight remain in the P5 service path. Audit failure keeps staging in place so an update proposal is not silently lost.
- Regression coverage: update reject preserves published + deletes staging + writes `review_reject_update`; update reject audit failure preserves staging; net-new reject remains unchanged; approve republish remains unchanged; Web reject update no longer returns "review entry is not available".
- Codex smoke results: net-new reject created deprecated; update reject preserved published and removed staging; deprecated same-id remained `E_DUP`; P5 review suite passed `26 passed`; full suite passed `222 passed`.
