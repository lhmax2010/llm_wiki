# Phase 5 Review Prompt - Staging Review

请对 Phase 5 PR 做高风险 review（三路：Claude + ChatGPT + Kimi）。

## 背景

Phase 1 已建立内容核 schema/storage/validation 与三态目录纪律。
Phase 2 已建立 Governed API pipeline、RBAC、audit，并修复 role/diff/id/audit 信任边界问题。
Phase 3 已建立 MCP wrapper，并修复 id/path traversal 进入 research 的问题。
Phase 4 已建立索引检索层，并修复 symlink/trust_state 绕过问题。

Phase 5 是发布闸门：`staging/` 待审条目经 reviewer approve 后进入 `entries/`，会立即暴露给 MCP/search 的 agent 读路径。

## 本次范围

- 新增 `review/` package：
  - `list_review_queue()`
  - `approve_staging_entry()`
  - `reject_staging_entry()`
- reject 去 `deprecated/`，保留条目与 audit 痕迹，不删除。
- approve/reject 保留 ID，更新 `trust_state`、`reviewer`、`updated`。
- 扩展 audit record 可选字段：`review_level`、`decision`、`reviewer`、`note`。
- 新增 `tests/review/test_service.py`。

## 专项必查 1：approve/reject 原子性与三态一致

重点检查：

- 是否所有按 id 读取 staging/entries/deprecated 的入口都先校验 `^KB-\d{4}-\d{4}$`。
- 是否使用 `resolve(strict=True)` 并确认 resolved path 在白名单目录内。
- 是否复用 P1 `read_entry()` / `write_entry()` / `validate_entry()`，没有裸 move 或手写 YAML 拼接。
- approve 后是否保证：
  - 目标路径为 `kb/entries/<id>.md`
  - `trust_state=published`
  - ID 不变
  - 写后再次 validate
- reject 后是否保证：
  - 目标路径为 `kb/deprecated/<id>.md`
  - `trust_state=deprecated`
  - ID 不变
  - audit 中能区分 `review_reject`
- audit append 失败是否回滚新写 target，且保留 staging 源文件。
- 源文件删除失败是否返回失败并记录日志，而不是伪装成功。

请尝试构造：

- staging 文件 `trust_state=published`。
- `entry_id="../research/..."`。
- staging symlink 指向 entries/research/deprecated。
- target 已存在时的覆盖尝试。
- audit 写失败、source unlink 失败。

## 专项必查 2：权限复用 P2 RBAC，不重新发明

重点检查：

- approve/reject 是否通过 `RolesConfig.permissions_for_user()` 解析 user -> role/permissions。
- 是否不信调用方自报 role。
- light 是否要求 `review_light`，heavy 是否要求 `review_heavy`。
- approve 是否额外要求 `publish_entry`。
- reject 是否额外要求 `deprecate_entry`。
- admin `*` 是否仍可通过。

请尝试构造：

- contributor approve/reject。
- 只有 `review_light` 的 reviewer 审 heavy。
- 调用方尝试把 heavy 自报成 light（当前 API 不接受自报 review_level；review_level 来自 audit，缺失默认 heavy）。

## 专项必查 3：audit 与 review_level 系统事实

重点检查：

- P2 audit 是否记录 `review_level`，供 P5 queue/approve/reject 使用。
- 旧 audit 缺失 `review_level` 是否保守按 heavy。
- approve/reject audit 是否记录：reviewer、decision、review_level、note、entry_id、target_dir、相对 path。
- reject 到 `deprecated/` 与“曾发布后废弃”是否至少能通过 audit operation 区分。

## 明确不做

- 不做 Web review UI。
- 不做 research promote（P6）。
- 不做复杂工作流引擎、动态审批规则、request_changes。
- 不改 P1-P4 核心行为。
- 不做 index 增量刷新，只保留 TODO。

## 验证命令

- `uv run ruff format . --check`
- `uv run ruff check .`
- `uv run mypy core tests governed-api mcp index scripts review`
- `uv run pytest --cov --cov-report=term-missing -q`

## 输出要求

请按严重度输出：

- `[BLOCKER]`：合并前必须修。
- `[MAJOR]`：强烈建议合并前修。
- `[MINOR]`：可进入 TODO，但请说明风险。
- `[NIT]`：风格或可读性建议。
