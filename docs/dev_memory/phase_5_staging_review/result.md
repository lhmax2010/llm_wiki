# Phase 5 - Staging Review / Result

## 最终状态

已 Merge。Phase 5 已通过 PR #5 合并到 `main`；三路 review 的合并前 BLOCKER/MAJOR/MINOR 修复项已闭环；checkpoint tag：`checkpoint/phase_5_staging_review`。

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
  - 已用单测覆盖 staging queue、approve/reject 三态流转、light/heavy RBAC、audit 留痕、audit 失败回滚、source cleanup warning、终态互斥、per-entry lock、目录 symlink 防护。

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/5
- 对应 Git Commit：
  - `7a26423` - `Merge pull request #5 from lhmax2010/phase/5-staging-review`
  - `c8ea6a9` - `[Phase 5] docs: dev_memory 收尾 + 陈旧锁 TODO`
  - `cdb4237` - `[Phase 5] fix: R14 instruction file follow-up`
  - `9688394` - `[Phase 5] fix: R14 review closure`
  - `47513ca` - `[Phase 5] staging review lifecycle`

## Review 状态

- 风险档：高风险。
- Review：Claude + ChatGPT + Kimi 三路 review 已完成。
- R14 修复状态：
  - FIX-1 BLOCKER：终态互斥 + per-entry lock。
  - FIX-2 BLOCKER：状态目录 symlink/escape 防护。
  - FIX-3 MAJOR：reject 放宽为 id/state/read 处置路径，queue 不因 stale evidence 隐藏条目。
  - FIX-4 MINOR：源清理失败改为 ok + `warning.field=staging_residue`。
  - FIX-5 MINOR：id regex 改 fullmatch。
- Review prompt：`docs/review/phase_5_review_prompt.md`

## 遗留问题 / 风险

- 跨目录状态流转不是数据库事务；当前保守顺序保证不会静默成功，最坏是可检测的重复 staging 残留。
- per-entry lock 正常路径用 `try/finally` 释放；硬崩/断电可能残留 `.lock`，单 id 后续 review 会持续 `E_DUP`，可手动删除对应锁恢复。后续可加锁超时/PID 检查或 SQLite review state CAS。
- approve/reject 后未自动刷新 P4 index；沿用 P4 rebuild/fallback 策略，增量刷新留后续。
- `review_level` 权威源当前来自 audit 日志，后续应按 R1 设计变更持久化到 frontmatter 或 SQLite review state。

## 下一阶段计划

- Phase 6：research 隔离与 promote flow。

## 2026-07-06 Post-Merge Fix Prepared: PR #12

- Fix scope: P5 review lifecycle only. `propose_update` reject now mirrors P8 approve republish semantics without deprecating the existing published entry.
- Root cause: approve republish had a dedicated update mode, while reject update proposals still followed the net-new reject path and collided with the existing published terminal entry.
- Outcome: update reject appends `review_reject_update`, deletes only the staging proposal, keeps `entries/{id}.md` unchanged, and does not create `deprecated/{id}.md`.
- Verification:
  - `uv run pytest` -> `222 passed, 1 warning`
  - `uv run pytest tests/review/test_service.py --no-cov` -> `26 passed`
  - Frontend: `npm run lint`, `npm run test`, and `npm run build` passed
  - Codex smoke confirmed net-new reject, update reject, deprecated same-id `E_DUP`, and approve republish regression safety
