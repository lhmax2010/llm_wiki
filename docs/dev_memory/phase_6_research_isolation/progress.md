# Phase 6 - Research Isolation / Progress

> 当下记录，不事后补编。Phase 6 的核心原则是“填预留位置，不新开绕过口子”。

## 关键决策

- research 使用独立 ID 命名空间 `R-YYYY-NNNN`。
  - 原因：research 是未验证线索，不应混入正式 KB `KB-YYYY-NNNN` 发号序列。
  - promote 到 draft 时重新通过 P1 `IDAllocator` 生成新的 `KB-YYYY-NNNN`，research 原件保留，draft 是一次新的正式化尝试。

- TTL 只做标记/统计，不自动删除。
  - 原因：research 是原始线索材料，过期表示“需人工复核”，不是“可安全丢弃”。
  - `ttl_report()` 返回 expired/active 数量和 expired ids，后续 UI/health check 可以展示。

- `research_index` 与 `agent_search_index` 物理分离。
  - research 数据只进入 `research_search_index` 独立 DB。
  - agent/human index 仍只从 P4 白名单源目录读取，不把 research 加入源目录。
  - research index 读取复用 P4 的路径纪律：`resolve(strict=True)`、确认在 `kb/research/` 内、目录 symlink 拒绝、坏文件跳过。

- `search_research_for_hints` 只返回 signal，不返回完整 research record。
  - signal 包含 `id/title/snippet/tags/created/expires_at/score/warning`。
  - `warning=unverified_research，不可用于判责` 明确提醒 agent 不能把 research 当正式知识或证据。

- research 写入双层阻断 agent。
  - P2 `auth_context` 对 `create_research/update_research/promote_research_to_draft` 检查 `author_type=agent` 并拒绝。
  - `ResearchStore` 也检查 `AuthorType.AGENT`，避免绕过 middleware 的内部调用直接写 research。
  - MCP 层不暴露 create/update/promote research 工具。

- research evidence 禁用放在 P1 `validate_entry()`。
  - 原因：P2 pipeline、MCP propose、P5 approve 等写入路径都会复用 P1 validation。
  - 覆盖 entry-level credibility evidence 和 section-level evidence。

## 已实现

- 新增 `research/` 包：
  - `ResearchRecord`
  - `ResearchIdAllocator`
  - `ResearchStore`
  - `read_valid_research_from_source`
  - `write_research_record`

- 更新 `index/search.py`：
  - `ResearchSearchIndex` 从 placeholder 变成真实索引。
  - `SearchService.search_research()` 支持 opt-in hints。
  - agent/human index 未加入 research 源目录。

- 更新 `mcp/kb_server/handlers.py`：
  - `search_research_for_hints()` 检查 `search_research_for_hints` 权限。
  - 返回 `research_signals`。

- 更新 `core/validation.py`：
  - 引用 `R-YYYY-NNNN`、`research/...`、`kb/research/...` 或 `/research/` 的 evidence 报 `E_RESEARCH_AS_EVIDENCE`。

- 更新 `governed-api/governed_api/middleware.py`：
  - research 操作权限映射。
  - agent author_type 阻断 research 写操作。

## 排除的方案

- 不沿用 research id 作为 draft id。
  - 这样会让未验证线索 ID 与正式 KB ID 混淆，也让 promote 看起来像原地升级。

- 不把 research signals 设计成完整 `SearchResult`。
  - `SearchResult` 面向正式 KB 条目，包含结构化可信度字段；research 只能给线索，不给正式知识视图。

- 不做自动删除 TTL。
  - 自动删 research 会丢线索，Phase 6 只暴露状态，处置留给人工流程。

## TODO / 后续

- research promote lock 与 P5 review lock 类似：进程硬崩时可能残留 `.lock`，需手动清理；后续可加锁超时/PID 检查。
- research index 当前是全量 rebuild + query-time Python 过滤；性能优化留后续健康/规模化阶段。
- TTL report 后续需要接入 health check 或 Web 展示。
- research create/update 的更细 owner 语义后续可扩展；Phase 6 先按角色权限控制。
