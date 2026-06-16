# Phase 5 - Staging Review / Result

## 当前状态

待 review。Phase 5 已完成 staging queue、approve、reject 的核心 service 与单测；PR #5 已创建，三路 review 的合并前必修项已按 R14 修复并推送等待复核。

## 测试情况

- 静态检查：
  - `uv run ruff format . --check` -> `45 files already formatted`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp index scripts review` -> `Success: no issues found in 45 source files`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `139 passed in 9.51s`
  - Total coverage: `92.72%`
  - touched review/governed files coverage snapshot:
    - `review/__init__.py`: `100%`
    - `review/service.py`: `81%`
    - `governed-api/governed_api/audit.py`: `90%`
    - `governed-api/governed_api/types.py`: `100%`
- 集成/端到端验收：
  - Phase 5 无 Web/API E2E。
  - 已用单测覆盖 staging queue、approve/reject 三态流转、light/heavy RBAC、audit 留痕、audit 失败回滚、source cleanup 失败告警。

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/5
- 对应 Git Commit：
  - `9688394` - `[Phase 5] fix: R14 review closure`
  - `47513ca` - `[Phase 5] staging review lifecycle`

## Review 状态

- 风险档：高风险。
- Review 计划：Claude + ChatGPT + Kimi 三路 review。
- R14 修复状态：
  - FIX-1 BLOCKER：终态互斥 + per-entry lock。
  - FIX-2 BLOCKER：状态目录 symlink/escape 防护。
  - FIX-3 MAJOR：reject 放宽为 id/state/read 处置路径，queue 不因 stale evidence 隐藏条目。
  - FIX-4 MINOR：源清理失败改为 ok + `warning.field=staging_residue`。
  - FIX-5 MINOR：id regex 改 fullmatch。
- Review prompt：`docs/review/phase_5_review_prompt.md`

## 遗留问题 / 风险

- 跨目录状态流转不是数据库事务；当前保守顺序保证不会静默成功，最坏是可检测的重复 staging 残留。
- 多 reviewer 并发已用 per-entry lock 收紧；后续如需 crash-safe stale lock 清理，可改 SQLite review state CAS。
- approve/reject 后未自动刷新 P4 index；沿用 P4 rebuild/fallback 策略，增量刷新留后续。
- `review_level` 权威源当前来自 audit 日志，后续应按 R1 设计变更持久化到 frontmatter 或 SQLite review state。

## 下一步

- 创建 PR #5，发起三路 review。
