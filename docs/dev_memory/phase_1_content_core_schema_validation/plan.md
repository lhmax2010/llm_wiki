# Phase 1 - Content Core Schema Validation / Plan

## 目标

Phase 1 建立统一知识库的内容核基础，让人和 agent 未来都能围绕同一份 Markdown/YAML 条目做读写、校验和治理。目标是先把 schema、证据映射、ID 发号、目录状态一致性和基础存储打牢，供后续 Governed API、MCP、索引和 Web 层复用。

## 范围边界

本阶段做：

- 四类正式 `entry_type` 的 Pydantic schema：`defect_case`、`triage_rule`、`code_flow`、`log_baseline`。
- Markdown 段落骨架校验，包含必需 heading、未知 heading、重复 heading、fenced code block 内 heading 忽略。
- `claim_type <- evidence` 证据映射：可降级时返回 normalized claim + `W_DOWNGRADE`，不可降级时返回错误。
- 证据存在性基础校验：`code` 证据走 `git ls-files`，`log/attachment` 证据查 `kb/attachments/`。
- SQLite ID 发号：按年份序列生成 `KB-YYYY-NNNN`，并发下保证唯一。
- SQLite 发号重建：扫描 `entries/`、`staging/`、`drafts/`、`deprecated/`，排除 `research/`，取 max+1，允许空洞。
- 三态/多态物理目录与 `trust_state` 冗余校验：目录状态不一致返回 `E_SCHEMA`。
- `code_binding` 字段形状/格式校验：路径、hash 字符串长度、枚举值等。
- Markdown + YAML frontmatter 读写 helpers。
- Phase 1 单元测试、覆盖率、review prompt 和 PR。

本阶段不做：

- Governed API middleware pipeline、RBAC、audit。
- MCP tools。
- staging/review/publish 流转。
- 搜索、索引、同义词扩展。
- `research/` 业务隔离、promote、TTL。
- 真实 hash 计算、clangd/tree-sitter 调用、stale 检测。
- Web 前端、collector、Kona 接入。

## 计划步骤

1. 读取 v1.3 设计、规约和 hash 口径，确认 Phase 1 范围不再有设计阻塞。
2. 增加 Phase 1 必需依赖：Pydantic v2 和 PyYAML。
3. 建立 `core/` 模块：models、errors、validation、id_allocator、storage。
4. 实现四类条目的 schema 和段落骨架校验。
5. 实现证据映射、证据形状校验和证据存在性校验。
6. 实现 SQLite ID allocator 和 rebuild 逻辑。
7. 实现目录状态与 `trust_state` 一致性校验。
8. 实现 `code_binding` shape-only 校验。
9. 补高风险路径测试：并发发号、重建、证据降级/打回、目录状态、code_binding、frontmatter。
10. 跑 `ruff format`、`ruff check`、`mypy`、`pytest --cov`。
11. 运行本地 Claude/Codex review，修复高/中风险发现。
12. 创建 Phase 1 PR，交给三路 review 继续闭环。

## 依赖前置阶段

无。Phase 1 是 DAG 的第一层基础阶段。

