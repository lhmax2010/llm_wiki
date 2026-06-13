# 设计变更 change_1：Phase 1 设计 Review 发现的 5 项

- 触发：Phase 1 启动前 R1 设计 Review（Codex 以实现者视角通读 design v1.2）
- 日期：2026-06-13
- 结果：design v1.2 → v1.3（5 项全部采纳）
- 影响范围：§3.4 schema、§4.1.3 证据映射、§4.2.1 发号、§4.4 CodeBinding、§7 Phase 1 范围

## 变更项

### 1. ID 口径统一为 SQLite 发号
- 问题：Phase 1 范围 + §3.4 注释残留 "git-derived ID"，与 §4.2.1 的 SQLite 发号矛盾（v1.1 改并发时遗漏同步）
- 改：统一为 SQLite 发号，去掉 git-derived 残留

### 2. CodeBinding 补字段
- 问题：hash_spec.md 要 symbol_hashes/build_config_hash/symbol_resolution，但 §4.4 CodeBinding 没有
- 改：§4.4 CodeBinding 补这三个字段

### 3. SQLite 重建扫描纳入 deprecated/
- 问题：重建只扫 entries/staging/drafts，若最高 ID 在 deprecated/ 会重复发号
- 改：扫描纳入 deprecated/（research 不在内，用独立标识）

### 4. observation 证据精确到 EvidenceType
- 问题：证据映射表 observation 行只写"观测记录"，太模糊
- 改：明确为 log/repro/ticket/human_note/attachment（任一，满足字段条件）

### 5. Phase 1 code_binding 只校验字段形状，不算真实 hash
- 问题：避免 P1 拉进 clangd/tree-sitter 致依赖膨胀
- 改：P1 只校验 hash 字段形状/格式合法；真实 hash 计算 + stale 检测留健康检查脚本（§5.4 后续 Phase）

## 处理
开发者确认，design 升 v1.3。Codex 据 v1.3 开始 Phase 1。
