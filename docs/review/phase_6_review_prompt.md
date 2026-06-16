# Phase 6 代码 Review 请求（统一知识库 · research 物理隔离 · 三路 review）

## 怎么 review

代码在 workspace（分支 `phase/6-research-isolation`）。重点看：
- `research/store.py`
- `index/search.py`
- `mcp/kb_server/handlers.py`
- `core/validation.py`
- `governed-api/governed_api/middleware.py`
- `tests/research/test_store.py`
- `tests/index/test_search.py`
- `tests/mcp/test_handlers.py`
- `tests/core/test_validation.py`

设计基线：`docs/design.md` v1.4，重点 §4.1.1 MCP 工具、§4.2.2 三态隔离、§4.2.3 RBAC、§5.2 安全、§7 Phase 6。

## 背景

Phase 6 填前序 Phase 预留的 research 线：
- P3 `search_research_for_hints` stub -> 真实 opt-in research signals。
- P4 `research_index` placeholder -> 独立 research index。
- 新增 research create/update/promote/TTL。
- P1 禁止 research 作为 formal evidence。

核心纪律：research 是未验证线索，默认对 agent 主搜索物理不可见；只可显式 opt-in 获取提示信号；promote 只能生成 draft，不能绕过 review。

## 已通过

- 聚焦测试：`103 passed`
- 全量无 coverage：`158 passed`
- mypy 聚焦：`Success: no issues found in 48 source files`
- ruff F/E9 聚焦：`All checks passed!`

## ★ 专项 1：agent 主搜索物理不含 research

请重点挖：
- `agent_search_index` / `search_kb` 是否仍然只扫 entries（include_pending 只加 staging），没有把 research 加进源目录。
- `research_search_index` 是否独立 DB，不能被 agent 主搜索误用。
- research index 的扫描是否复用路径防护：resolve、is_relative_to、目录 symlink 拒绝、坏文件跳过。
- 是否存在 fallback 或 direct scan 新路径绕过 P3/P4 隔离。

## ★ 专项 2：search_research_for_hints 是显式 opt-in 且只返回 signal

请重点挖：
- 是否检查 `search_research_for_hints` 权限。
- 返回字段是否只是 `research_signals`，不含完整 body/evidence/frontmatter。
- warning 是否明确标注 unverified research 不可用于判责。

## ★ 专项 3：promote 不绕过 review

请重点挖：
- promote 是否复制到 `drafts/`，不是原地改 research。
- draft 是否用新的 `KB-YYYY-NNNN`，不是沿用 `R-YYYY-NNNN`。
- research 原件是否保留。
- draft 是否 `trust_state=draft`，后续仍需 propose/review/publish，不直接进入 staging/entries。
- 是否有 audit、duplicate 防护、lock 防并发、写后 validate。

## ★ 专项 4：agent 不能写 research

请重点挖：
- P2 `auth_context` 是否阻断 `author_type=agent` 的 research create/update/promote。
- `ResearchStore` 是否也阻断 agent，防内部调用绕过 middleware。
- MCP 是否没有暴露 create/update/promote research 工具。

## ★ 专项 5：research 不能作为 evidence

请重点挖：
- P1 `validate_entry()` 是否覆盖 entry-level credibility evidence。
- 是否覆盖 section-level evidence。
- 是否能识别 `R-YYYY-NNNN`、`research/...`、`kb/research/...`、`/research/`。
- P2/P3/P5 是否自动继承这个禁用，不需要重复实现。

## 其他重点

- TTL 是否只标记/统计、不自动删除。
- Research ID allocator 是否与 KB ID allocator 分开。
- 错误码是否沿用现有码，不乱加新语义。
- Windows 路径/符号链接场景是否有遗漏。

## 输出格式

```
# Phase 6 Review by [你]
## ★ 专项1：agent 主搜索物理不含 research
## ★ 专项2：opt-in signals only
## ★ 专项3：promote 不绕过 review
## ★ 专项4：agent 不能写 research
## ★ 专项5：research evidence 禁用
## BLOCKER / MAJOR / MINOR / NIT
## 总体：可合并 / 改后可合并 / 有 BLOCKER
```
