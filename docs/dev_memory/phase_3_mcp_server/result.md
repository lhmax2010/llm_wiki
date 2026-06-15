# Phase 3 - MCP Server / Result

## 当前状态

已 Merge。Phase 3 MCP server V1 已通过 PR #3 合并到 `main`；三路 review 后的 R14 修复（FIX-1 到 FIX-7）已闭环，两个 BLOCKER 已复核通过。checkpoint tag：`checkpoint/phase_3_mcp_server`。

## 测试情况

- 静态检查（ruff/mypy）：
  - `uv run ruff format .` -> `32 files left unchanged`
  - `uv run ruff check .` -> `All checks passed!`
  - `uv run mypy core tests governed-api mcp` -> `Success: no issues found in 32 source files`
- 单测 + 覆盖率：
  - `uv run pytest --cov --cov-report=term-missing -q` -> `104 passed in 6.17s`
  - Total coverage: `93.07%`
  - touched mcp coverage snapshot:
    - `mcp/kb_server/__init__.py`: `100%`
    - `mcp/kb_server/handlers.py`: `80%`
    - `mcp/kb_server/server.py`: `69%`
    - `mcp/kb_server/types.py`: `100%`

## PR 与代码

- PR 链接：https://github.com/lhmax2010/llm_wiki/pull/3
- 对应 Git Commit：
  - `e8c5ce9` - `Merge pull request #3 from lhmax2010/phase/3-mcp-server`
  - `fafa107` - `[Phase 3] mcp server wrapper`
  - `917d438` - `[Phase 3] fix: R14 id path guard and MCP robustness`
  - `42df17a` - `[Phase 3] docs: record R14 fix commit`
  - `6651f0e` - `[Phase 3] chore: remove external fix instructions from repo`
  - `176ebd4` - `[Phase 3] docs: dev_memory 收尾`

## Review 状态

- 风险档：普通风险。
- Review 方式：Kimi + Claude Opus + ChatGPT-Codex。
- R14：FIX-1 到 FIX-7 已修复并补测试；两个 BLOCKER 修法已复核通过。
- 专项必查：
  - MCP wrapper 是否绕过 Phase 2 七段 Governed API pipeline。
  - `search_kb` / `get_entry` 是否物理不可见 research。
- Review prompt：`docs/review/phase_3_review_prompt.md`

## 遗留问题 / 风险

- P3 未引入官方 MCP SDK；当前为最小 JSON-RPC stdio wrapper。若后续要换官方 SDK，需按 R8 单独做依赖决策。
- P3 search 是 storage 直扫版，默认只扫 `entries/`，`include_pending=True` 额外扫 `staging/`；P4 再实现索引/同义词/CJK/ranking。
- `search_research_for_hints` 仅 stub，返回空 `research_signals`；真实 research 逻辑留 P6。
- `phase3_fix_instructions.md` 是外部 review 指令文档，已从 repo 移除。
- `_require` 里的 `if not role` 是死代码，已记入 `progress.md` TODO，后续清理。

## 下一步

- 按 DAG 进入下一 Phase 前置；继续继承 Phase 2 pipeline 信任边界和 Phase 3 research 物理不可见约束。
