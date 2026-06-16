# 维护 Skill（行为契约）

面向诊断型 agent 的知识维护契约。你在输出最终诊断前，要检查相关 KB 条目是否仍匹配当前代码和现象；发现腐烂风险时，只能通过 MCP `propose_update` 提交维护建议。

## 目标

- 防止过期 `code_binding`、旧日志基线或旧排查规则继续误导诊断。
- 在诊断报告里留下维护动作摘要，让人知道你检查了哪些条目。
- 用 P1-P5 既有治理链路处理 stale 标记，不新增任何写入路径。

## 适用场景

- 一次缺陷诊断、回归分析、线上问题复盘或代码路径排查即将结束。
- 你引用了 KB 条目，或发现 KB 条目与当前代码/日志不一致。
- 你怀疑某个 published/pending 条目的 `code_binding` 已过时。

## 使用的 MCP 工具

- `search_kb(query, scope?, include_pending?, expand_synonyms?, limit?, offset?, sort?)`
- `get_entry(id)`
- `propose_update(id, patch, reason, credibility?, request_id)`

这些工具是唯一维护入口。skill 不要求 agent 接触文件系统、SQLite、audit 或 review 队列。

## 强制维护检查点

1. 在最终诊断前，用 `search_kb(query, expand_synonyms=true, include_pending=true)` 搜相关模块、错误码、日志签名、函数名和同义说法。
2. 对每条会影响诊断的结果，用 `get_entry(id)` 回读完整结构，重点看：
   - `code_binding.repo_id`
   - `code_binding.git_sha`
   - `code_binding.paths`
   - `code_binding.symbols`
   - `code_binding.path_hashes`
   - `code_binding.symbol_hashes`
   - `code_binding.build_config_id`
   - `code_binding.stale`
   - `code_binding.stale_reason`
3. 对比当前代码事实：
   - 相关 path/symbol 不存在、语义明显改变、签名改变、日志含义改变：提交 stale 更新。
   - 只有仓库整体 SHA 改变，但相关 path/symbol 未变：不要批量标 stale。
   - 拿不准但风险会影响诊断：提交 stale 更新，并把 `stale_reason` 写成“待人工复核”的具体原因。
4. 需要标 stale 时，调用 `propose_update`，patch 只改必要字段，例如：
   - `code_binding.stale=true`
   - `code_binding.stale_reason="<具体差异和复核建议>"`
   - 正文补一个维护说明段落或 `OPEN` 项。
5. 处理返回的 `warnings` / `errors`。被打回时不要绕过；在诊断报告里说明维护建议未成功提交以及原因。
6. 在最终诊断报告末尾写维护摘要：`已检查 N 条 KB，引用 M 条，提交 stale 更新 K 条，失败 F 条`。

## stale 判断

- 标 stale：相关 `paths` / `symbols` 在当前代码中不存在、行为变了、入口/出口条件变了、日志签名含义变了。
- 不标 stale：只是不相关文件变化，或条目没有 `code_binding` 且你没有发现具体过期事实。
- 保守标注：若条目直接影响当前诊断且你不能确认其仍正确，用 `stale_reason` 写清不确定点，并让 review 接手。

## 证据纪律

- 维护建议也必须给 evidence：代码差异、日志差异、测试输出或诊断观察。
- 你提供 evidence；系统裁决 `claim_type` 和 review 等级。不要自报高可信度来压过治理。
- `stale_reason` 必须具体到 path/symbol/log/现象，不能只写“可能过期”。

## 禁止事项

- 不直接改 published 条目。
- 不因为仓库 SHA 改变就批量标 stale。
- 不新增 review、audit、index 或权限逻辑。
- 不把 research 内容作为物理可见的 KB 搜索结果处理。
