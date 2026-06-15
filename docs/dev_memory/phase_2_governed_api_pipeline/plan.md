# Phase 2 - Governed API Pipeline / Plan

## 目标

实现 Governed API 的 V1 middleware pipeline，让 Web/MCP/Collector 未来都能通过同一条治理链路写入内容核。

设计依据：
- `docs/design.md` §4.2.1：`request -> auth_context -> schema_validate -> evidence_validate -> classify_write_route -> review_route -> persist -> audit_append`
- `docs/design.md` §4.4：`MiddlewareContext` / `MiddlewareResult`
- `docs/design.md` §7 Phase 2：Governed API pipeline，依赖 P1
- Phase 1 dev_memory：内容核 schema、证据映射、SQLite 发号、三态目录一致性、`code_binding` shape-only 校验已经合并

baseline commit：`924ec2dd1092b0fa4fdc5363363d1bc741f3dd30`（Phase 1 merge 后 main 登记提交）

## 范围边界

本阶段做：
- 在现有 `governed-api/` 目录下建立 Python package（实际 import package 拟用 `governed_api`，避免连字符目录名无法导入）。
- 定义 `MiddlewareContext` / `MiddlewareResult` / API error 等 V1 结构，保持与 design §4.4 字段语义一致。
- 实现 pipeline 顺序执行器，按段落返回 `ok/context/error`，失败时停止后续 middleware。
- 实现 `auth_context`：从调用方身份/角色/权限构造 context；加载 `config/roles.yaml`。
- 实现 `schema_validate`：把 payload 转成 Phase 1 `core.models.Entry`，处理 Pydantic/schema 错误。
- 实现 `evidence_validate`：调用 Phase 1 `core.validation.validate_entry()`，复用证据形状、证据存在性、证据映射降级/打回、三态一致性和 `code_binding` shape-only 校验，不重写规则。
- 实现 `classify_write_route`：按 design §4.2.1 的编辑分级规则，决定 `target_dir` / 写入路由。
- 实现 `review_route`：按 `auto/light/heavy` 设置 review level；V1 保守默认 heavy。
- 实现 `persist`：V1 用 Phase 1 `IDAllocator` + `core.storage.write_entry()` 写入 Markdown；遵守 SQLite 发号再写 git markdown，允许号烧掉不复用。
- 实现 `audit_append`：V1 简化，只记录谁、何时、哪条、什么操作，不记完整 diff。
- 实现 RBAC decorator / permission helper：YAML 驱动，轻量 permission 检查。
- 补 `tests/governed_api/` 单测与集成测试，覆盖每段 middleware、pipeline 停止语义、RBAC YAML、编辑分级、persist/audit 基本闭环。

本阶段不做：
- 不实现复杂 RBAC policy engine、动态工作流配置、可视化规则编辑器、复杂审计查询。
- 不实现 staging 生命周期 service、review UI、人工审批队列 UI。
- 不碰 MCP server、Web App、Collector、Index/Search、Research 隔离层。
- 不重新实现 Phase 1 的 schema/evidence/code_binding/hash 规则；`evidence_validate` 只调用 `core.validation.validate_entry()`。
- 不计算真实 `path_hash` / `symbol_hash` / `build_config_hash`，不接 clangd/tree-sitter，不做 stale 检测。
- 不修改 Frozen design；若发现 §4.2.1/§7 口径冲突或接口缺口，按 R1 停下报 `[DESIGN_ISSUE]`。

## 计划步骤

1. 确认 Phase 2 风险档并等待用户确认。
2. restate Phase 2 的交付范围、文件改动、七段 pipeline 输入输出、简化项和 DoD；等待用户确认后再编码。
3. 建立 `governed-api/governed_api/` package 与 `tests/governed_api/` 测试布局。
4. 实现类型与错误模型：context/result/api error/audit record/route/review level。
5. 实现 roles YAML loader 与 `require_permission(...)` decorator/helper，覆盖 reader/contributor/reviewer/admin。
6. 实现七段 pipeline：`auth_context`、`schema_validate`、`evidence_validate`、`classify_write_route`、`review_route`、`persist`、`audit_append`。
7. 补独立 UT：每段 middleware 输入输出、失败停止、权限拒绝、编辑分级保守默认、audit V1 记录内容。
8. 补集成测试：合法 create/propose 走完整 pipeline；schema/evidence 错误阻止 persist；persist 写入正确目录并产生 audit。
9. 开发中持续追加 `progress.md` 关键决策和排除方案。
10. 跑三道门：`uv run ruff format .`、`uv run ruff check .`、`uv run mypy core tests governed-api`、`uv run pytest --cov --cov-report=term-missing -q`，记录真实输出。
11. 生成 review prompt，提交 PR，按高风险三路 review 执行 R14 闭环。

## 依赖前置阶段

- Phase 1：已 Merge，checkpoint `checkpoint/phase_1_content_core`。
- 直接复用：
  - `core.models.Entry`
  - `core.validation.validate_entry()` / `ValidationReport`
  - `core.storage.write_entry()` / `target_dir_for_trust_state()`
  - `core.id_allocator.IDAllocator`
  - `core.errors.ValidationIssue` / `IssueCode`
- 现有依赖：`pydantic>=2,<3`、`PyYAML>=6,<7`、pytest/ruff/mypy。Phase 2 暂无新增业务依赖计划；如实现中确需新增依赖，按 R8 先停下报批。
