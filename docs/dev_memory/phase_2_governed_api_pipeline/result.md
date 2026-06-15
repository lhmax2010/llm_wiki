# Phase 2 - Governed API Pipeline / Result

## 当前状态

待 Review。Phase 2 V1 Governed API pipeline 已完成本地实现与测试，PR 已创建，进入高风险三路 review（Claude + ChatGPT + Kimi）。

## 测试情况

- 静态检查（ruff/mypy）：
  - `uv run ruff format .` -> `24 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api` -> `Success: no issues found in 24 source files`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `76 passed in 5.16s`
  - Total coverage: `95.50%`
  - touched governed-api coverage snapshot:
    - `governed-api/governed_api/__init__.py`: `100%`
    - `governed-api/governed_api/audit.py`: `100%`
    - `governed-api/governed_api/middleware.py`: `89%`
    - `governed-api/governed_api/pipeline.py`: `100%`
    - `governed-api/governed_api/roles.py`: `84%`
    - `governed-api/governed_api/types.py`: `100%`

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/2
- 对应 Git Commit：
  - `d942bae` - `[Phase 2] governed API middleware pipeline`

## Review 状态

- 风险档：高风险。
- 计划 review：Claude + ChatGPT + Kimi。
- Review prompt：`docs/review/phase_2_review_prompt.md`

## 遗留问题 / 风险

- update 精细分级依赖调用方提供 `previous_payload` / `previous_entry` / `changed_fields` / `change_scopes`；Phase 2 不在 classify 段隐式读 storage。缺少 diff 信息时保守 heavy。
- audit V1 只 append JSONL；不做审计查询，不记录完整 diff。
- `auth_context` 不做登录/session/token；后续 Web/API 层负责。
- `review_route` 不做 review 队列、审批流或 UI；P5 处理。
- MCP、research 隔离业务、Web、Collector、Index/Search 均未实现；按 Phase DAG 留给后续阶段。

## 下一步

- 创建 PR，执行高风险三路 review。
- 按 R14 闭环 BLOCKER/MAJOR/MINOR。
- Review 通过后更新本文件状态、PR commit、INDEX，再 merge 和打 checkpoint tag。
