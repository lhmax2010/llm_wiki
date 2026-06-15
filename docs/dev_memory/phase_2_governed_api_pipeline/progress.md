# Phase 2 - Governed API Pipeline / Progress

> 开发过程持续追加，记录思考与决策，而非仅结果。

## 关键决策

- 决策：pipeline runner 采用顺序执行 + fail-fast 中断语义。
  - 原因：Governed API 是所有写入口的共同治理链路，某段失败后继续执行会造成未校验写盘、错误 audit 或 review 分级被绕过。每段只通过 `MiddlewareContext` 传递状态，返回 `MiddlewareResult(ok/context/error)`；`ok=False` 时立即停止后续 middleware。
  - 排除的方案：排除“收集所有错误后继续跑完整 pipeline”，因为 `persist` 和 `audit_append` 有副作用；排除异常驱动主流程，因为 design §4.4 已冻结 result 结构。

- 决策：`classify_write_route` 对 update 做精细分级时不在 middleware 内隐式读取旧条目；调用方必须提供 `previous_payload` / `previous_entry` 或 `changed_fields`。
  - 原因：Phase 2 的职责是治理 pipeline，不是完整 storage service。若 classify 段自行按 ID 读旧条目，会把路径解析、状态目录、权限和存储错误耦合进分级逻辑，扩大 middleware。没有旧内容或 changed_fields 时，update 保守进入 heavy review。
  - 排除的方案：排除在 classify 段调用 storage 读盘做 diff；排除没有 diff 时猜测为 auto/light；排除 Phase 2 只支持 create，因为 update 分级规则可以用显式输入先落地。

- 决策：RBAC V1 只做 YAML 角色权限加载 + `require_permission(...)` helper/decorator。
  - 原因：design §4.2.1 明确 ACL 不进 pipeline，放 handler decorator；§4.2.3 也要求 YAML 驱动。Phase 2 只提供可测试的权限入口，后续 Web/MCP handler 使用它。
  - 排除的方案：排除复杂 policy engine、角色继承语法、动态工作流和管理 UI；`admin: ["*"]` 仅作为通配权限处理。

- 决策：`evidence_validate` 必须把 `repo_root` / `kb_root` 显式传给 Phase 1 `core.validation.validate_entry()`；`entry_path` 若调用方已知则透传，persist 生成真实写入路径后再重校验一次。
  - 原因：Phase 1 R14 FIX-1 证明缺少 `repo_root` 时证据存在性可能被绕过；Phase 2 作为治理入口必须 fail-loud，不能静默跳过 evidence lookup。pipeline 顺序中 `evidence_validate` 早于 `classify_write_route`，create 场景此时还没有最终目录，所以三态目录一致性在 `persist` 用最终 path 重校验兜底。
  - 排除的方案：排除在 P2 重新实现证据形状或存在性规则；排除默认关闭 `check_evidence_exists`。

- 决策：create/propose payload 缺 `id` 时，`schema_validate` 使用内部占位 ID 通过纯 schema/evidence 校验，真实 ID 只在 `persist` 段由 SQLite allocator 分配。
  - 原因：design §4.1/§4.4 写明创建请求不含 id，由 SQLite 发号；但 Phase 1 `Entry` 模型代表完整条目，`id` 必填。若在 `schema_validate` 直接发号，会让纯校验段产生副作用，并在后续 validation/classify 失败时提前烧号。占位 ID 只在内存中存在，`persist` 前会被真实 ID 替换。
  - 排除的方案：排除让调用方自己预分配 ID；排除放宽 Phase 1 `Entry.id` 必填；排除在 schema_validate 调 SQLite。

- 决策：`persist` 写盘前用最终 `target_dir` + 真实 ID 再跑一次 `core.validation.validate_entry()`。
  - 原因：`review_route` 会根据 auto/light/heavy 调整 `trust_state`，`persist` 才知道最终 path；写盘前重校验能捕获目录与 `trust_state` 不一致，避免绕过 Phase 1 三态纪律。若重校验失败，已经分配的 ID 按 Phase 1 规则允许烧掉，不回收。
  - 排除的方案：排除只信 evidence_validate 的早期结果直接写盘；排除失败后回滚 SQLite 序列，因为 P1 明确唯一性优先于连续性。

## 进度日志

- [2026-06-15] Phase 2 开分支 `phase/2-governed-api-pipeline`，baseline `924ec2d`。
- [2026-06-15] 创建 `plan.md` 并更新 dev_memory INDEX；风险档确认为高风险，三路 review。
- [2026-06-15] 用户确认 restate 后开始编码；先记录 pipeline 中断、diff 来源、RBAC 简化、evidence_validate 复用 P1 的关键决策。
- [2026-06-15] 完成 `governed-api/governed_api/` V1 package、七段 middleware、RBAC YAML helper、audit append 和 pipeline runner。
- [2026-06-15] 补 `tests/governed_api/`：覆盖每段 middleware、pipeline 中断、update 保守分级、create 发号写盘、audit、validation failure 阻止 persist。
- [2026-06-15] 本地门禁结果：`uv run ruff format .` -> `24 files left unchanged`；`uv run ruff check .` -> `All checks passed!`；`uv run mypy core tests governed-api` -> `Success: no issues found in 24 source files`；`uv run pytest --cov --cov-report=term-missing -q` -> `76 passed in 5.16s`，总覆盖率 `95.50%`，`middleware.py` 覆盖率 `89%`。

## TODO

- 收尾时记录真实 R13 命令输出、覆盖率、PR 链接和 review/R14 状态。
