# Phase 2 - Governed API Pipeline / Progress

> 开发过程持续追加，记录思考与决策，而非仅结果。

## 关键决策

- 决策：pipeline runner 采用顺序执行 + fail-fast 中断语义。
  - 原因：Governed API 是所有写入口的共同治理链路，某段失败后继续执行会造成未校验写盘、错误 audit 或 review 分级被绕过。每段只通过 `MiddlewareContext` 传递状态，返回 `MiddlewareResult(ok/context/error)`；`ok=False` 时立即停止后续 middleware。
  - 排除的方案：排除“收集所有错误后继续跑完整 pipeline”，因为 `persist` 和 `audit_append` 有副作用；排除异常驱动主流程，因为 design §4.4 已冻结 result 结构。

- 决策：`classify_write_route` 对 update 做精细分级时，系统只根据 `previous_payload` / `previous_entry` 与当前 `entry` 的实际 diff 裁决；调用方传入的 `changed_fields` / `change_scopes` 只作为"只升不降"提示。
  - 原因：Phase 2 的职责是治理 pipeline，不是完整 storage service。若 classify 段自行按 ID 读旧条目，会把路径解析、状态目录、权限和存储错误耦合进分级逻辑；但如果直接信任调用方自报 diff，又会让重操作伪装成 typo 绕过 heavy review。因此旧内容必须作为系统事实输入，diff 在 middleware 内实算；缺少旧内容时保守 heavy。
  - 排除的方案：排除在 classify 段调用 storage 读盘做 diff；排除信任调用方自报 `changed_fields` / `change_scopes` 下调 review；排除没有 diff 时猜测为 auto/light。

- 决策：RBAC V1 只做 YAML 角色权限加载 + `require_permission(...)` helper/decorator。
  - 原因：design §4.2.1 明确 ACL 不进 pipeline，放 handler decorator；§4.2.3 也要求 YAML 驱动。Phase 2 只提供可测试的权限入口，后续 Web/MCP handler 使用它。
  - 排除的方案：排除复杂 policy engine、角色继承语法、动态工作流和管理 UI；`admin: ["*"]` 仅作为通配权限处理。

- 决策：`evidence_validate` 必须把 `repo_root` / `kb_root` 显式传给 Phase 1 `core.validation.validate_entry()`；`entry_path` 若调用方已知则透传，persist 生成真实写入路径后再重校验一次。
  - 原因：Phase 1 R14 FIX-1 证明缺少 `repo_root` 时证据存在性可能被绕过；Phase 2 作为治理入口必须 fail-loud，不能静默跳过 evidence lookup。pipeline 顺序中 `evidence_validate` 早于 `classify_write_route`，create 场景此时还没有最终目录，所以三态目录一致性在 `persist` 用最终 path 重校验兜底。
  - 排除的方案：排除在 P2 重新实现证据形状或存在性规则；排除默认关闭 `check_evidence_exists`。

- 决策：create/propose payload 缺 `id` 时，`schema_validate` 使用内部占位 ID 通过纯 schema/evidence 校验，真实 ID 只在 `persist` 段由 SQLite allocator 分配。
  - 原因：design §4.1/§4.4 写明创建请求不含 id，由 SQLite 发号；但 Phase 1 `Entry` 模型代表完整条目，`id` 必填。若在 `schema_validate` 直接发号，会让纯校验段产生副作用，并在后续 validation/classify 失败时提前烧号。占位 ID 只在内存中存在，`persist` 前会被真实 ID 替换。
  - 排除的方案：排除让调用方自己预分配 ID；排除接受 create/propose payload 自带 ID；排除放宽 Phase 1 `Entry.id` 必填；排除在 schema_validate 调 SQLite。

- 决策：`auth_context` 的 role 只从 `roles_config.users` 映射解析；请求自带 role 必须与映射一致，否则 `E_PERM`。
  - 原因：role 是权限事实，不是调用方声明。若 user 能自报 admin，所有后续 operation permission 和 review 边界都失效。permissions 始终基于系统解析出的 role 重新计算。
  - 排除的方案：排除请求 role 优先；排除未知 user 携带 role 后临时放行；排除在 P2 引入 session/login，登录仍留给 Web/API 层。

- 决策：`persist` 写盘前用最终 `target_dir` + 真实 ID 再跑一次 `core.validation.validate_entry()`。
  - 原因：`review_route` 会根据 auto/light/heavy 调整 `trust_state`，`persist` 才知道最终 path；写盘前重校验能捕获目录与 `trust_state` 不一致，避免绕过 Phase 1 三态纪律。若重校验失败，已经分配的 ID 按 Phase 1 规则允许烧掉，不回收。
  - 排除的方案：排除只信 evidence_validate 的早期结果直接写盘；排除失败后回滚 SQLite 序列，因为 P1 明确唯一性优先于连续性。

## 进度日志

- [2026-06-15] Phase 2 开分支 `phase/2-governed-api-pipeline`，baseline `924ec2d`。
- [2026-06-15] 创建 `plan.md` 并更新 dev_memory INDEX；风险档确认为高风险，三路 review。
- [2026-06-15] 用户确认 restate 后开始编码；先记录 pipeline 中断、diff 来源、RBAC 简化、evidence_validate 复用 P1 的关键决策。
- [2026-06-15] 完成 `governed-api/governed_api/` V1 package、七段 middleware、RBAC YAML helper、audit append 和 pipeline runner。
- [2026-06-15] 补 `tests/governed_api/`：覆盖每段 middleware、pipeline 中断、update 保守分级、create 发号写盘、audit、validation failure 阻止 persist。
- [2026-06-15] 首轮本地门禁结果：`uv run ruff format .` -> `24 files left unchanged`；`uv run ruff check .` -> `All checks passed!`；`uv run mypy core tests governed-api` -> `Success: no issues found in 24 source files`；`uv run pytest --cov --cov-report=term-missing -q` -> `76 passed in 5.16s`，总覆盖率 `95.50%`，`middleware.py` 覆盖率 `89%`。
- [2026-06-15] Phase 2 三路 review R14：按根因总纲修复"middleware 信任调用方自我声明"问题。统一原则：安全相关输入（role/diff/id）都由系统事实裁决，不信自报。
- [2026-06-15] R14 修复后最终门禁结果：`uv run ruff format .` -> `24 files left unchanged`；`uv run ruff check .` -> `All checks passed!`；`uv run mypy core tests governed-api` -> `Success: no issues found in 24 source files`；`uv run pytest --cov --cov-report=term-missing -q` -> `83 passed in 5.06s`，总覆盖率 `95.39%`，`middleware.py` 覆盖率 `89%`。

## R14 修复记录

- FIX-1【BLOCKER】：role 自报提权。
  - 修复思路：`auth_context` 只通过 `roles_config.permissions_for_user(user)` 从 `users` 映射解析 role 和权限；请求中若带 role，必须与映射一致，否则 `E_PERM`；未知 user fail-closed。
  - 测试：`test_auth_context_rejects_missing_user_role_mismatch_and_unknown_user` 覆盖 reader 自报 admin 和未知用户自报 role。

- FIX-2【BLOCKER】：`changed_fields` / `change_scopes` 伪造绕 review。
  - 修复思路：`classify_write_route` 改为用 previous/current Entry 的实际 diff 计算 review level；调用方声明只通过 `_classify_claimed_change()` 参与"只升不降"。无 previous 时保守 heavy。
  - 测试：`test_self_reported_diff_cannot_downgrade_actual_heavy_change` 覆盖真实改 claim_type 但自报 typo/tags 仍 heavy；`test_update_auto_scope_can_auto_publish` 覆盖真实 auto diff 才能 auto。

- FIX-3【BLOCKER】：create/propose payload 自带 id 绕过 SQLite 发号。
  - 修复思路：`schema_validate` 对 create/propose 自带 `id` 直接 `E_SCHEMA(payload.id)`；缺 id 时只放内部占位 ID，`persist` 再调用 SQLite allocator 生成真实 ID。
  - 测试：`test_schema_validate_rejects_create_payload_with_self_declared_id`；原 create persist 测试继续断言 `allocated_id == KB-2026-0001`。

- FIX-4【BLOCKER】：persist 后 audit 失败导致无审计落盘。
  - 修复思路：`run_pipeline` 顶层捕获 middleware 异常并归一为 `MiddlewareResult(ok=False)`；`persist` 写盘前 preflight audit path；`audit_append` 失败时删除刚写入但未审计的 entry 文件。
  - 测试：`test_pipeline_catches_exceptions_and_rolls_back_unaudited_write`、`test_audit_failure_rolls_back_persisted_entry`。

- FIX-5【MAJOR】：reviewer 漏 contributor 权限。
  - 修复思路：`config/roles.yaml` 展开 reviewer 权限，显式包含 `create_research` / `edit_own_research` / `propose_entry` / `promote_research_to_draft`。
  - 测试：`test_load_roles_config_and_admin_wildcard` 覆盖 reviewer 具备 `propose_entry` 和 `create_research`。

- FIX-6【MINOR】：operation 级权限校验缺失。
  - 修复思路：`auth_context` 在解析权限后按 operation 检查最小 permission，例如 create/propose/update 需要 `propose_entry`，reader create 直接 `E_PERM`。
  - 测试：`test_auth_context_enforces_operation_permission`。

- FIX-7【MINOR】：`E_VALIDATION` off-contract。
  - 修复思路：删除自造 `E_VALIDATION`，validation 失败时 `ApiError.code` 使用第一条 `ValidationIssue.code` 的真实值，如 `E_SCHEMA` / `E_EVIDENCE_MISSING`。
  - 测试：`test_evidence_validate_surfaces_core_errors`、`test_persist_revalidates_target_dir_before_write`、`test_validation_failure_prevents_persist_and_audit`。

- FIX-8【MINOR】：`write_entry` 非原子写。
  - 修复思路：`core.storage.write_entry()` 改为同目录临时文件写入，完成后 `os.replace()` 原子替换，异常时清理 temp。
  - 测试：`test_write_entry_is_atomic_when_replace_fails`。

- FIX-9【MINOR】：audit 记录绝对路径。
  - 修复思路：`build_audit_record()` 记录相对 `kb_root` 的 POSIX path，避免泄漏服务器绝对路径/用户名。
  - 测试：`test_persist_allocates_id_writes_entry_and_audit` 断言 audit path 为 `staging/KB-2026-0001.md` 且非绝对路径。

- FIX-10【MINOR】：`roles.yaml` agent 注释误导。
  - 修复思路：注释改为 P6/P10b 定义独立 agent 角色，且不得包含 `create_research/promote` 权限；强制机制留 P6。

## TODO

- agent 不能 create/update research 的强制机制（author_type=agent 阻断）留 P6 实现。
- 失败/拒绝操作也写 audit，作为安全事件追溯。
- 同 id 并发 update 丢更新：低并发 V1 可接受，后续 storage service/乐观锁处理。
- persist 重复跑整套 validate 的性能：后续可只补 path/目录态校验，避免重复 git 子进程。
- NIT：context 浅拷贝隐患、ApiError.details 序列化、build_audit_record 用 `.get` 防御。
