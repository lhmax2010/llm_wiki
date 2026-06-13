# 端到端验收清单（替代原 SOP 的真机 test-guide）

每个 Phase 的第三道门（集成/端到端验收）清单放这里。
见 docs/DEV_GUIDE.md 步骤 D 的验收对照表。

例：P6 research 隔离验收清单（关键）：
- [ ] agent 主搜索（search_kb）物理搜不到 research 条目
- [ ] research 不能作为正式条目的 evidence（E_RESEARCH_AS_EVIDENCE）
- [ ] agent 不能 create/update research
- [ ] promote_research_to_draft 复制生成 draft，不原地改状态
- [ ] research TTL 到期提醒
- [ ] search_research_for_hints 走独立返回字段 research_signals
