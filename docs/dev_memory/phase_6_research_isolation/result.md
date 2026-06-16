# Phase 6 - Research Isolation / Result

## 当前状态

已 Merge。Phase 6 已通过 PR #7 合并到 `main`；checkpoint tag：`checkpoint/phase_6_research_isolation`。R14 的 1 个 BLOCKER、4 个 MAJOR、4 个 MINOR 已闭环，FIX-1/FIX-2 已确认是真修。

## 测试情况

- 静态检查：
  - `uv run ruff format .` -> `1 file reformatted, 52 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core governed-api mcp index review research scripts tests --show-error-codes` -> `Success: no issues found in 53 source files`
- 聚焦测试：
  - `uv run pytest tests/core/test_validation.py tests/governed_api/test_middleware.py tests/research/test_store.py tests/index/test_search.py tests/mcp/test_handlers.py -q --no-cov` -> `115 passed in 4.69s`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `170 passed in 13.00s`
  - Total coverage: `91.36%`

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/7
- 对应 Git Commit：
  - `f31e3ef` - `Merge pull request #7 from lhmax2010/phase/6-research-isolation`
  - `84337f4` - `[Phase 6] docs: dev_memory 收尾 + URL编码 NIT TODO`
  - `d17e3b0` - `[Phase 6] research isolation`
  - `ffa8d7a` - `[Phase 6] docs: add PR link`
  - `f216888` - `[Phase 6] fix: R14 research isolation closure`

## Review 状态

- 三路 review 已完成，发现 1 BLOCKER + 4 MAJOR + 4 MINOR。
- FIX-1 到 FIX-9 已修复并补测试。
- FIX-1/FIX-2 已确认是真修；其余修复随 PR 合并。

## 遗留问题 / 风险

- promote 公共 helper 尚未抽取；已记 TODO，不阻塞本轮。
- research promote lock 硬崩残留需要后续清理机制。
- TTL 只报告不删除，需要后续 UI/health check 消费。

## 下一步

- Phase 7：Web human reader/editor。
