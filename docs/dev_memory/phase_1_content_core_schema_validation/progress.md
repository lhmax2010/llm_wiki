# Phase 1 - Content Core Schema Validation / Progress

> 开发过程持续追加，记录思考与决策，而非仅结果。

## 关键决策

- 决策：SQLite 发号使用 `BEGIN IMMEDIATE` + 按年份序列。
  - 原因：设计 v1.3 明确 ID 口径为 SQLite 发号，不再使用 git-derived 旧口径。`BEGIN IMMEDIATE` 在分配前拿写锁，让多个 agent/Web 写入者在同一个 SQLite 文件上串行领取 ID，优先保证唯一性。按年份建序列可保持 `KB-YYYY-NNNN` 可读性，重建时扫描正式 ID 目录取 max+1，允许空洞但不回收 ID。
  - 排除的方案：排除了 git commit/hash 派生 ID，因为 v1.3 已冻结为 SQLite 发号；排除了纯文件锁，因为 Windows/跨进程可靠性不如 SQLite 事务；排除了 UUID，因为不符合 `KB-YYYY-NNNN` 设计；排除了全局不分年份序列，因为会破坏 ID 语义。

- 决策：证据映射以 evidence 驱动，降级链在 `validate_entry()` / `_normalize_credibility()` 内集中实现。
  - 原因：Phase 1 要把可信度纪律放在内容核入口，而不是相信作者声明。`fact` 缺少强证据时先降为 `observation`，若 observation 证据也不成立再降为 `llm_hypothesis`；`historical_pattern` 缺少 `historical_entry` 时降为 `llm_hypothesis`；`static_inference` 缺少 code 证据、`spec` 缺少 spec+version 时直接打回。entry 级 credibility 先归一化，section 级再继承或覆盖，section 有本地 evidence 时会把降级结果写回 normalized section，避免 warning 和返回状态不一致。
  - 排除的方案：排除了只报 warning 不改 normalized claim 的方案，因为 agent 消费时容易继续误用高可信字段；排除了所有不符一律打回，因为 design §4.1.3 明确部分 claim_type 可降级；排除了把证据映射推迟到 P2 middleware，因为 Phase 1 DoD 要求纯代码校验可落地。

- 决策：三态/多态一致性以物理目录为主，frontmatter `trust_state` 为冗余校验，不一致直接 `E_SCHEMA`。
  - 原因：design 把物理分目录作为防泄漏边界，尤其避免 `research/` 或 draft 内容靠布尔过滤误进 agent 主视图。目录是更便宜、更可审计的边界；frontmatter 可以被人或 agent 写错，所以只能作为可读元数据和一致性校验对象。
  - 排除的方案：排除了只信 `trust_state` 字段的方案，因为漏过滤会破坏隔离；排除了把不一致降为 warning 的方案，因为目录/状态错位会影响后续索引、权限和 agent 可见性；排除了 Phase 1 自动搬文件的方案，因为流转和 publish 属于后续治理层。

- 决策：`code_binding` Phase 1 只校验字段形状，不计算真实 hash。
  - 原因：v1.3 明确 Phase 1 只做字段形状/格式校验，不调用 clangd/tree-sitter，也不做 stale 检测。Phase 1 校验路径为 repo-relative POSIX path，hash 为固定长度 lowercase hex，`symbol_resolution` 为枚举，从而保证后续健康检查脚本和索引层有稳定输入。
  - 排除的方案：排除了在 P1 调 clangd/tree-sitter 的方案，因为这会引入工具链、编译配置和性能复杂度，越过 P1 范围；排除了完全不校验 `code_binding` 的方案，因为后续真实 hash 计算需要字段形状先稳定；排除了用 git sha 派生 path/symbol hash 的方案，因为 `docs/hash_spec.md` 已把真实 hash 口径独立出来。

- 决策：Markdown heading 提取忽略 fenced code block，重复 heading 返回 `E_SCHEMA`。
  - 原因：`code_flow` 和 `log_baseline` 条目天然可能嵌入代码、日志、Markdown 片段，fence 内 `##` 不应被当作知识库段落 heading。重复 heading 会让 section-level credibility 的映射对象不唯一，应作为 schema 错误。
  - 排除的方案：排除了简单 regex 全文扫描 heading 的方案，因为 Claude review 指出会误拒合法条目；排除了允许重复 heading 的方案，因为会让段落级可信度不可判定。

- 决策：非 UTF-8 entry 文件在 storage/rebuild 入口 fail fast。
  - 原因：ID rebuild 如果静默忽略坏字节，可能漏扫已有 `KB-YYYY-NNNN` 并重新发出重复 ID。storage 读取也应给出清晰错误，避免后续校验拿到损坏内容。
  - 排除的方案：排除了 `errors="ignore"` 静默读取；排除了在 Phase 1 尝试自动修复编码，因为技能库/历史文件编码问题属于迁移或后续维护任务。

## 改动摘要

- 文件/模块：`core/models.py`
  - 改动内容：实现 design §4.4 的 Pydantic v2 schema、枚举、严格字段模型和 schema_version=3 校验。

- 文件/模块：`core/errors.py`
  - 改动内容：定义 Phase 1 使用的错误/警告码和 `ValidationIssue`。

- 文件/模块：`core/validation.py`
  - 改动内容：实现段落骨架、证据映射、证据形状/存在性、目录状态和 `code_binding` shape-only 校验。

- 文件/模块：`core/id_allocator.py`
  - 改动内容：实现 SQLite 年度序列、`BEGIN IMMEDIATE` 分配、rebuild 扫描、4 位 ID 上限和 UTF-8 frontmatter 读取。

- 文件/模块：`core/storage.py`
  - 改动内容：实现 Markdown/YAML frontmatter 读写和 trust_state 到目录的映射 helper。

- 文件/模块：`tests/core/`
  - 改动内容：覆盖四类条目、证据降级/打回、并发发号、重建、目录状态、路径形状、frontmatter、fenced heading、重复 heading 等高风险路径。

## 进度日志

- [2026-06-13] 完成 Phase 1 restate，确认高风险三路 review，明确不做 API/MCP/search/hash 计算。
- [2026-06-13] 经用户批准安装 `pydantic>=2,<3` 和 `PyYAML>=6,<7`，企业网络下使用 `uv --system-certs`。
- [2026-06-13] 完成 content-core 初版，实现 schema、validation、ID allocator、storage 和测试。
- [2026-06-13] 首轮本地门禁通过后运行 Claude review，发现目录状态定位、裸 log 证据、rebuild 扫描正文 ID 等问题并修复。
- [2026-06-13] 二轮 Claude read-only review 继续发现 fenced code block heading false positive 等问题；已修复并补测试。
- [2026-06-13] 最终本地门禁：`ruff format`、`ruff check`、`mypy`、`pytest` 通过，`38 passed`，总覆盖率 `96.01%`。
- [2026-06-13] `codex review --uncommitted` 受 Windows sandbox `CreateProcessWithLogonW failed: 1385` 阻塞，记录为未通过本地 Codex review。
- [2026-06-13] 创建 PR https://github.com/lhmax2010/llm_wiki/pull/1，等待 ChatGPT/Kimi 外发 review 和 R14 闭环。
- [2026-06-15] 按新版 SOP 把单文件 dev_memory 重组成 `plan.md` / `progress.md` / `result.md` 三件套。

