# Checkpoints

> 每个 Phase 合并后登记 tag、commit、验收摘要和回退指令。

| tag | commit | 验收摘要 | 回退指令 | 回退影响 |
|-----|--------|----------|----------|----------|
| `checkpoint/phase_1_content_core` | `3751bcea2a18f3d1449e8433822d782e0eac58ec` | Phase 1 内容核、Pydantic schema、证据映射、SQLite 发号、三态目录、code_binding shape-only 校验；PR #1 四路 review/R14 闭环；`48 passed`，coverage `96.84%`。 | `git switch main && git reset --hard checkpoint/phase_1_content_core` | 回退到 Phase 1 合并点；后续 Phase 需重做或重新合并。 |
| `checkpoint/phase_2_governed_api` | `b0a54ed72cf062d407753f429424eaf30b61492e` | Phase 2 Governed API middleware pipeline、RBAC、audit、persist 复用 Phase 1 core；PR #2 三路 review/R14 修复 role/diff/id/audit 信任边界；`85 passed`，coverage `95.49%`。 | `git switch main && git reset --hard checkpoint/phase_2_governed_api` | 回退到 Phase 2 合并点；后续 Phase 需重做或重新合并。 |
| `checkpoint/phase_3_mcp_server` | `e8c5ce90935d17202b31fbd148b54e4a350137d3` | Phase 3 MCP server 7 工具，propose 复用 Phase 2 pipeline，search/get_entry 守住 research 隔离；PR #3 三路 review/R14 修复 path traversal 和 propose_update 绕发号；`104 passed`，coverage `93.07%`。 | `git switch main && git reset --hard checkpoint/phase_3_mcp_server` | 回退到 Phase 3 合并点；后续 Phase 需重做或重新合并。 |
| `checkpoint/phase_4_index_search` | `8c33dbd9faf6d3c9057d821ace70d7c09517b5f6` | Phase 4 索引检索层，同义词、CJK bigram、min_support、agent/human path catalog、research_index placeholder、MCP search 切索引加 fallback；PR #4 三路 review/R14 修复 symlink 和坏 trust_state 绕过；`120 passed`，coverage `93.56%`。 | `git switch main && git reset --hard checkpoint/phase_4_index_search` | 回退到 Phase 4 合并点；后续 Phase 需重做或重新合并。 |
| `checkpoint/phase_5_staging_review` | `7a26423165904fe79dbd83edd475ff4660a15524` | Phase 5 staging review 发布闸门，queue、approve/reject、light/heavy RBAC、audit 留痕、reject 到 deprecated；PR #5 三路 review/R14 修复终态互斥和目录 symlink 两个 BLOCKER；`139 passed`，coverage `92.72%`。 | `git switch main && git reset --hard checkpoint/phase_5_staging_review` | 回退到 Phase 5 合并点；后续 Phase 需重做或重新合并。 |
