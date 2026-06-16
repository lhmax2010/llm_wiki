# Phase 6 - Research Isolation / Progress

> 当下记录，不事后补编。Phase 6 的核心原则是“填预留位置，不新开绕过口子”。R14 后补充：research 写入路径也必须完整继承 P1-P5 的纪律。

## 关键决策

- research 使用独立 ID 命名空间 `R-YYYY-NNNN`。
  - research 是未验证线索，不应混入正式 KB `KB-YYYY-NNNN` 发号序列。
  - promote 到 draft 时通过 P1 `IDAllocator` 生成新的 `KB-YYYY-NNNN`，research 原件保留。

- TTL 只做标记/统计，不自动删除。
  - research 是原始线索材料，过期表示“需人工复核”，不是“可安全丢弃”。
  - `ttl_report()` 返回 expired/active 数量和 expired ids，后续 UI/health check 可消费。

- `research_index` 与 `agent_search_index` 物理分离。
  - research 数据只进入 `research_search_index` 独立 DB。
  - agent/human index 仍只从 P4 白名单源目录读取，不把 research 加入源目录。
  - research index 读取复用 P4 路径纪律：`resolve(strict=True)`、确认在 `kb/research/` 内、目录 symlink 拒绝、坏文件跳过。

- `search_research_for_hints` 只返回 signal，不返回完整 research record。
  - R14 后按 design §4.4 收敛为 `id/title/snippet/trust_state/warning`。
  - `warning=unverified_research，不可用于判责` 明确提醒 agent 不能把 research 当正式知识或证据。

- research 写入采用 fail-closed author_type。
  - P2 `auth_context` 对 `create_research/update_research/promote_research_to_draft` 要求系统侧 `author_type=human`；缺失或 `agent` 都拒绝。
  - `ResearchStore` 同样要求 `AuthorType.HUMAN`，避免内部调用绕过 middleware。
  - 当前没有身份系统可自动派生 author_type，所以选择“未知即拒绝”，由 Web/API 集成层提供系统事实。

- research evidence 禁用放在 P1 `validate_entry()`。
  - P2 pipeline、MCP propose、P5 approve 等写入路径都会继承。
  - 覆盖 entry-level credibility evidence 和 section-level evidence。

## R14 根因总纲

三路 review 确认主隔离守住了：agent 主搜索物理不含 research、research_index 复用 P4 路径防护、promote 没直接进正式发布路径。

但 research 新写入/校验路径只继承了一半纪律，漏了 P1-P5 的另一半：不信自报、检测要全、权限要 enforce、audit 失败回滚、幂等要跨终态。修复统一原则：research 写入要和主链路一样严。

## R14 FIX

- FIX-1 BLOCKER：research evidence URI 绕过。
  - `_research_reference()` 现在大小写归一，覆盖 `research:` / `research://` scheme、`research/` 路径、`kb/research/` 路径、`/research/` 路径，以及任意字段里的 `R-YYYY-NNNN` 子串。
  - 补测试覆盖 `research:R-2026-0001`、`research://R-2026-0001`、大写 scheme、human_note 子串。

- FIX-2 MAJOR：author_type fail-open。
  - P2 middleware 对 research 写操作缺 `author_type` 或非 `human` 一律 `E_PERM`。
  - `ResearchStore.author_type` 默认改为 `None`，只有 `AuthorType.HUMAN` 允许写。
  - 补测试覆盖缺 author_type fail-closed。

- FIX-3 MAJOR：`edit_own_research` 未 enforce own。
  - `update_research()` 读取磁盘 `record.author` 后比较 `self.user`，非 owner 拒绝；admin `*` 可越权。
  - 补测试覆盖 bob 不能改 alice 的 research，alice 可改。

- FIX-4 MAJOR：update audit 失败留下未审计内容。
  - `update_research()` audit append 失败时把旧 `ResearchRecord` 写回磁盘；rollback 失败会打 error log。
  - 补测试 monkeypatch audit append 抛错，断言 body 仍是 old。

- FIX-5 MAJOR：promote 幂等只查 drafts。
  - duplicate scan 扩到 `drafts/staging/entries`，识别 `source_refs[].type=research` 且 id 相同。
  - 补测试覆盖 draft 离开 drafts 到 staging/entries 后再次 promote 仍 `E_DUP`。

- FIX-6 MINOR：duplicate scan fail-open。
  - duplicate scan 任一源目录异常时 fail-closed，返回 `E_DUP` 阻止 promote。
  - 补测试 monkeypatch scan 抛 `ValueError`，断言不落 draft。

- FIX-7 MINOR：大小写检测并入 FIX-1。

- FIX-8 MINOR：ResearchIdAllocator 对齐 P1。
  - 使用本地时间默认年份。
  - 校验 year 在 1000-9999。
  - next number 超过 9999 抛 exhausted。
  - 补测试覆盖非法 year 和耗尽。

- FIX-9 MINOR：ResearchSignal 收敛到 §4.4。
  - 对外 signal 移除 `tags/created/expires_at/score`。
  - score/created 只留作内部排序。
  - 补测试断言 signal key 集合。

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
  - 返回 `research_signals`，不返回完整 body/evidence。

- 更新 `core/validation.py`：
  - research evidence 禁用覆盖 URI scheme、路径和 R-id 子串。

- 更新 `governed-api/governed_api/middleware.py`：
  - research 操作权限映射。
  - research 写操作 author_type fail-closed。

## 排除的方案

- 不沿用 research id 作为 draft id。
  - 这样会让未验证线索 ID 与正式 KB ID 混淆，也让 promote 看起来像原地升级。

- 不把 research signals 设计成完整 `SearchResult`。
  - `SearchResult` 面向正式 KB 条目；research 只能给线索，不给正式知识视图。

- 不做自动删除 TTL。
  - 自动删 research 会丢线索，Phase 6 只暴露状态，处置留给人工流程。

## TODO / 后续

- FIX-1 还有一个 NIT：`_research_reference()` 当前没有先做 URL decode，理论上 `research%3AR-2026-0001` 这类刻意 URL 编码的 research URI 仍可能绕过。概率极低且需要故意洗证据，后续可用 `urllib.parse.unquote()` 归一后再检测。
- promote 可抽公共 helper：当前纪律已到位（preflight audit、validate、write、post-validate、audit、rollback），但没有和 P5 共用 helper；后续可抽一个 review/publish/promote 共用的状态写入 helper。
- research promote lock 与 P5 review lock 类似：进程硬崩时可能残留 `.lock`，需手动清理；后续可加锁超时/PID 检查。
- research index 当前是全量 rebuild + query-time Python 过滤；性能优化留后续健康/规模化阶段。
- TTL report 后续需要接入 health check 或 Web 展示。
- research create/update 当前走 `ResearchStore` 而非 P2 pipeline；本轮已补齐权限/audit/rollback，后续可评估是否抽到统一 pipeline/helper。
