# Phase 2 - Governed API Pipeline / Result

## 当前状态

待 Merge。Phase 2 V1 Governed API pipeline 已完成三路 review 后的 R14 修复（FIX-1 到 FIX-10），并补充回滚失败告警；当前 PR #2 已更新，等待 merge。

## 测试情况

- 静态检查（ruff/mypy）：
  - `uv run ruff format .` -> `24 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api` -> `Success: no issues found in 24 source files`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `85 passed in 4.95s`
  - Total coverage: `95.49%`
  - touched governed-api coverage snapshot:
    - `governed-api/governed_api/__init__.py`: `100%`
    - `governed-api/governed_api/audit.py`: `92%`
    - `governed-api/governed_api/middleware.py`: `89%`
    - `governed-api/governed_api/pipeline.py`: `97%`
    - `governed-api/governed_api/roles.py`: `83%`
    - `governed-api/governed_api/types.py`: `100%`

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/2
- 对应 Git Commit：
  - `d942bae` - `[Phase 2] governed API middleware pipeline`
  - `bb1765f` - `[Phase 2] docs: add PR link`
  - `c2e0475` - `[Phase 2] fix: R14 governance trust boundary closure`
  - `58732a2` - `[Phase 2] fix: 回滚失败告警 + dev_memory 收尾`

## Review 状态

- 风险档：高风险。
- 三路 review：Claude + ChatGPT + Kimi 已完成。
- R14：FIX-1 到 FIX-10 已修复；回滚失败告警补丁已补。
- Review prompt：`docs/review/phase_2_review_prompt.md`

## 遗留问题 / 风险

- update 精细分级依赖系统侧提供 `previous_payload` / `previous_entry`；Phase 2 不在 classify 段隐式读 storage。缺少 previous 时保守 heavy。调用方 `changed_fields` / `change_scopes` 只允许升 review，不允许降级。
- audit V1 只 append JSONL；不做审计查询，不记录完整 diff。
- `auth_context` 不做登录/session/token；后续 Web/API 层负责。
- `review_route` 不做 review 队列、审批流或 UI；P5 处理。
- agent 不能 create/update research 的强制机制留 P6。
- 失败/拒绝操作也写 audit、同 id 并发 update 乐观锁、persist 重复 validate 性能优化留后续。
- MCP、research 隔离业务、Web、Collector、Index/Search 均未实现；按 Phase DAG 留给后续阶段。

## 下一步

- 等待 R14 复核确认。
- 复核通过后更新本文件状态、最终 commit、INDEX，再 merge 和打 checkpoint tag。
