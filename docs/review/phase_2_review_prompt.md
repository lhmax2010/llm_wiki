# Phase 2 Review Prompt - Governed API Pipeline

请对 Phase 2 PR 做高风险独立 review。重点找 correctness / security boundary / governance bypass 问题，按 BLOCKER / MAJOR / MINOR / NIT 标严重程度。

## 背景

- 项目：统一知识库，Web/MCP/Collector 未来都必须通过同一 Governed API pipeline 写入同一内容核。
- Phase 1 已合并：`core.models.Entry`、`core.validation.validate_entry()`、`core.storage.write_entry()`、`core.id_allocator.IDAllocator`。
- Phase 2 目标：实现 V1 middleware pipeline：
  `auth_context -> schema_validate -> evidence_validate -> classify_write_route -> review_route -> persist -> audit_append`

## 设计依据

- `docs/design.md` §4.2.1 Governed API middleware pipeline
- `docs/design.md` §4.4 `MiddlewareContext` / `MiddlewareResult`
- `docs/design.md` §7 Phase 2
- Phase 1 dev_memory：`docs/dev_memory/phase_1_content_core_schema_validation/`

## 本 PR 改动

- 新增 `governed-api/governed_api/`
  - `types.py`：`MiddlewareContext` / `MiddlewareResult` / `ApiError`
  - `pipeline.py`：顺序 runner，任一段 `ok=False` 立即中断
  - `roles.py`：YAML roles loader + `require_permission(...)`
  - `middleware.py`：七段 middleware
  - `audit.py`：V1 JSONL append audit
- 新增 `tests/governed_api/`
- 更新 `pyproject.toml`：pytest pythonpath 增加 `governed-api`
- 更新 Phase 2 dev_memory

## 请重点 review

1. pipeline 中断语义是否可靠：
   - 任一 middleware fail 后是否不会继续 persist/audit。
   - `MiddlewareResult(ok/context/error)` 是否和 design §4.4 对齐。

2. `evidence_validate` 是否真的复用 Phase 1：
   - 必须调用 `core.validation.validate_entry()`。
   - 必须传 `repo_root` / `kb_root`，不能重现 Phase 1 FIX-1 的存在性校验绕过。
   - 不应重写证据映射/降级/打回逻辑。

3. `classify_write_route` 是否保守且不膨胀：
   - create/propose 没 diff，必须 heavy。
   - update 没有 `previous_payload` / `previous_entry` / `changed_fields` / `change_scopes` 时，必须 heavy。
   - auto/light/heavy 规则是否符合 design §4.2.1。
   - 是否有把本该 heavy 的 claim/evidence/code_binding 关键变更放成 auto/light 的漏洞。

4. ID 分配与 persist：
   - create payload 不含 id 时，schema 阶段只用内存占位 ID，不应提前发号。
   - `persist` 才调用 `IDAllocator.allocate()`，再用 `core.storage.write_entry()`。
   - `persist` 写盘前是否用最终 `target_dir` + 真实 ID 重跑 `validate_entry()`，防三态目录错位。
   - 写盘失败/校验失败时 ID 烧掉不回收是否符合 Phase 1 决策。

5. RBAC V1 边界：
   - ACL 是否只在 `roles.py` helper/decorator，未塞入 pipeline。
   - `admin: ["*"]` 通配是否正确。
   - 是否误做了复杂 policy engine / role inheritance / session/login。

6. audit V1 边界：
   - 是否只 append 谁/何时/哪条/什么操作/目录/path。
   - 是否误做复杂 diff 或审计查询。
   - audit failure 的副作用语义是否可接受。

7. 范围边界：
   - 不应实现 MCP/P3、review UI 或审批队列/P5、research 隔离业务/P6、Web/Collector/Index/Search。

## 本地门禁

已在 Windows 本机执行：

```text
uv run ruff format .
24 files left unchanged

uv run ruff check .
All checks passed!

uv run mypy core tests governed-api
Success: no issues found in 24 source files

uv run pytest --cov --cov-report=term-missing -q
76 passed in 5.16s
Total coverage: 95.50%
governed-api/governed_api/middleware.py coverage: 89%
```

## 已知边界

- `auth_context` 不做登录/session/token，只补 role/permissions。
- `review_route` 只决策分级，不做 review 队列/审批流/UI。
- update 精细分级依赖调用方提供旧内容或变更标签；Phase 2 不在 classify 段隐式读 storage。
- `audit_append` V1 只 append JSONL，不做查询。
