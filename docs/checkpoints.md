# Checkpoints 登记

> 每个 Phase 完成打 tag 后在此登记（R3）。格式：tag | commit | 覆盖范围 | 回退指令 | 回退后状态

| tag | commit | 覆盖范围 | 回退指令 | 回退后状态 |
|-----|--------|----------|----------|------------|
| `checkpoint/phase_1_content_core` | `3751bcea2a18f3d1449e8433822d782e0eac58ec` | Phase 1 内容核、Pydantic schema、证据映射/校验、SQLite 发号与重建、三态目录一致性、code_binding shape-only 校验、dev_memory 三件套；PR #1 四路 review/R14 闭环，`48 passed`，coverage `96.84%`。 | `git switch main && git reset --hard checkpoint/phase_1_content_core` | 回到 Phase 1 合并完成、Phase 2 尚未开始的基线。 |
| `checkpoint/phase_2_governed_api` | `b0a54ed72cf062d407753f429424eaf30b61492e` | Phase 2 Governed API middleware pipeline；七段 middleware、roles.yaml ACL、audit append、persist 复用 Phase 1 core、三路 review/R14 闭环，含 role/diff/id/audit 信任边界修复与回滚失败告警，`85 passed`，coverage `95.49%`。 | `git switch main && git reset --hard checkpoint/phase_2_governed_api` | 回到 Phase 2 合并完成、Phase 3 尚未开始的基线。 |
| `checkpoint/phase_3_mcp_server` | `e8c5ce90935d17202b31fbd148b54e4a350137d3` | Phase 3 MCP server 7 工具；`propose_entry`/`propose_update` 复用 Phase 2 pipeline；`search_kb`/`get_entry` research 物理不可见；三路 review/R14 闭环，含 path traversal 读 research、`propose_update` 绕发号 2 BLOCKER 修复，`104 passed`，coverage `93.07%`。 | `git switch main && git reset --hard checkpoint/phase_3_mcp_server` | 回到 Phase 3 合并完成、后续 Phase 尚未开始的基线。 |
| `checkpoint/phase_4_index_search` | `8c33dbd9faf6d3c9057d821ace70d7c09517b5f6` | Phase 4 索引检索层；同义词扩展、CJK bigram、`min_support` 段落穿透、agent/human path catalog、`research_index` placeholder、MCP `search_kb` 索引优先+安全 fallback；三路 review/R14 闭环，含 symlink 逃逸进 research、坏 `trust_state` 绕过 2 BLOCKER 修复，`120 passed`，coverage `93.56%`。 | `git switch main && git reset --hard checkpoint/phase_4_index_search` | 回到 Phase 4 合并完成、Phase 5 尚未开始的基线。 |
