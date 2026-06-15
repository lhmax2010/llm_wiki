# Phase 1 - Content Core Schema Validation / Result

## 最终状态

待 Review。Phase 1 代码已完成并推送到当前 PR 分支，PR 已创建；四路 review 的合并前 BLOCKER/MAJOR/MINOR 修复项已处理，仍待复核和 merge，尚未打 checkpoint tag。

## 测试情况

- 静态检查（ruff/mypy）：
  - `uv run ruff format .` -> `10 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests` -> `Success: no issues found in 10 source files`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `47 passed in 4.75s`
  - Total coverage: `96.80%`
  - touched core files coverage snapshot:
    - `core/__init__.py`: `100%`
    - `core/errors.py`: `100%`
    - `core/id_allocator.py`: `89%`
    - `core/models.py`: `100%`
    - `core/storage.py`: `91%`
    - `core/validation.py`: `96%`
- 集成/端到端验收：
  - Phase 1 无 Web/API/MCP E2E。
  - 已用单测覆盖 Markdown/frontmatter roundtrip、git evidence lookup、attachment lookup、SQLite 并发发号和 rebuild。

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/1
- 对应 Git Commit：
  - `d950453` - `[Phase 1] content core schema validation`
  - `6ba0773` - `[Phase 1] add PR link to review prompt`

## Review 状态

- Claude 本地 read-only review：已完成。高/中风险发现已修复，最终复核结论为无 remaining correctness blockers / high / medium issues。
- Codex 本地 review：已尝试 `codex review --uncommitted`，但 Windows sandbox 阻塞，错误为 `CreateProcessWithLogonW failed: 1385`，不能视为通过。
- 四路 review R14：FIX-1 到 FIX-6 已修复并补测试；其余低风险项已记入 `progress.md` TODO。

## 遗留问题 / 风险

- `codex review --uncommitted` 在本机 Windows sandbox 下不可用，需要后续作为环境问题单独处理。
- `E_RESEARCH_AS_EVIDENCE` 未在 Phase 1 实现；按 design §7 属于 Phase 6 research 隔离层范围。
- 真实 `path_hash` / `symbol_hash` / `build_config_hash` 计算、clangd/tree-sitter、stale 检测未实现；按 v1.3 明确留给后续健康检查脚本。
- staging/review/publish 流转、RBAC、audit、MCP、search/index、Web、collector 均未实现；按 Phase DAG 留给后续阶段。
- checkpoint tag 尚未打；按新版 SOP，应在 review 闭环、PR merge 后再在 merge 后 commit 上打 tag。

## 下一阶段计划

- 完成 Phase 1 ChatGPT/Kimi 外发 review，按 R14 处理 BLOCKER/MAJOR/MINOR。
- Phase 1 merge 后更新 `result.md` 状态和 `docs/dev_memory/INDEX.md`，再打 checkpoint tag。
- Phase 2：Governed API middleware pipeline，包括 auth_context、schema_validate、evidence_validate、classify_write_route、review_route、audit_append。
