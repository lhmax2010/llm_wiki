# Phase 3 Review 闭环 — 修复清单（R14）

三路 review（Kimi / Claude Opus / ChatGPT-Codex）完成。**2 BLOCKER + 2 MAJOR 必修 + MINOR 一并修，其余记 TODO。**

## ★ 根因总纲（先理解）：id/路径必须先校验形状再用

P3 的两个 BLOCKER 是**同一类病的延续**——agent/调用方能提供 id 或路径的地方，没校验形状就直接拼路径用。这条线在前几个 Phase 反复出现：
- Phase 1 FIX-3：三态 fallback `../` 绕过
- Phase 2 BLOCKER-3：payload 自带 id 绕过发号
- **Phase 3 BLOCKER-1：get_entry id 含 `../research/` 穿越白名单读 research**
- **Phase 3 BLOCKER-2：propose_update patch 自带 id 绕过发号**

**统一防护原则**：凡是 agent/调用方能提供 id 或路径的入口，先强校验 id 形状（`^KB-\d{4}-\d{4}$`），再用；路径读取时 resolve().relative_to() 双保险确认没穿越。绝不直接拼 `f"{agent_id}.md"`。

这次不是逐个补洞——建立一个"id/路径入口统一校验"的防护，让所有 MCP 工具入口都过这道关。

---

## 必修（合并前）

### FIX-1【BLOCKER】get_entry path traversal 绕过 research 隔离（ChatGPT/Codex 实测，10/10）
- 位置：handlers.py:212 `_find_entry` 直接拼 `f"{entry_id}.md"`，不校验 id 形状
- 问题：`get_entry("../research/KB-2026-0004")` 返回 trust_state=research 的条目。专项 2（research 物理不可见）被 get_entry 这条路击穿。
- 修：① 所有按 id 读/写的入口（get_entry/propose_update/_find_entry）先强校验 `^KB-\d{4}-\d{4}$`，非法格式直接拒（含 `../` 的 id 会被挡）② 路径读取时 `resolve().relative_to(kb_root / allowed_dir)` 双保险，确认解析后路径仍在白名单目录内
- 补测试：get_entry("../research/...")、get_entry("../drafts/...")、各种畸形 id → 拒绝/not found，不返回 research

### FIX-2【BLOCKER】propose_update 缺旧条目用 patch 自带 id 绕过发号（三路一致）
- 位置：handlers.py:378 `_merge_update_payload` 的 `payload.setdefault("id", entry_id)`
- 问题：`propose_update(id="KB-2026-0001", patch.id="KB-2026-9999")` 写出 staging/KB-2026-9999.md。等于"update 不存在条目 = create with agent-chosen id"，绕过 SQLite 发号，后续 allocate 到同号会重号/覆盖。违反 Phase 1 发号唯一性。
- 修（用户定选项 A）：**previous_entry 为 None 时，propose_update 直接 E_SCHEMA "entry not found" 失败**（design §4.1.1：propose_update 针对既有条目，不是 upsert；要新建用 propose_entry）。同时无论旧条目是否存在，merge 后强制 `payload["id"] = entry_id`（不让 patch 自带 id 胜出）。
- 测试反转：`test_propose_update_without_previous_entry_can_still_run_as_heavy` 当前把错误行为当 feature 固化，改成断言"应失败（entry not found）"。
- 补测试：propose_update 不存在的 id → 失败；patch.id 与参数 id 不一致 → 以参数 id 为准。

### FIX-3【MAJOR】坏 .md 文件拖垮所有读工具（三路一致）
- 位置：handlers.py:231-234 `_read_entries_from_dir` 逐文件 read_entry，任一坏文件抛异常中断整个 search/list/browse
- 问题：entries/ 里一个坏文件 / README.md / schema 不合的 .md → 整个 agent 主读路径全挂。单点脆弱。
- 修：逐文件 try/except，坏文件跳过 + 记 warning/diagnostic（注意取舍：发号器对坏文件 fail-loud 是对的，但这里是读索引，应跳过而非全断，保证 agent 主读路径健壮）。
- 补测试：entries/ 放一个坏 .md / 非 entry .md → search 跳过坏文件返回合法条目，不全挂。

### FIX-4【MAJOR】server JSON 解析在 try 外，畸形输入 DoS 整个 server（Claude/ChatGPT MAJOR）
- 位置：server.py:42-67 `json.loads(line)` 和 `request.get("id")` 在 try 之外
- 问题：一条非法 JSON → JSONDecodeError 冒泡 → stdio 循环未捕获 → 服务进程死。合法 JSON 但非 object（5/[]）→ AttributeError 同样崩。一条畸形输入 DoS 整个 MCP server。
- 修：① json.loads + 类型检查纳入 try ② 非法 JSON 返回 -32700，非 object request 返回 -32600 ③ run_stdio_server 外层兜底 except，单行错误不杀循环
- 补测试：非法 JSON / 非 object 请求 → 返回 error，server 不崩继续服务。

## 一并修（MINOR）

### FIX-5【MINOR】MCP 协议层未捕获所有异常（Kimi MINOR-1，和 FIX-4 相关）
- handle_jsonrpc_line 只捕获部分异常，ValidationError/OSError 会顶穿。最外层捕获 Exception 返回 JSON-RPC internal error（-32603）。和 FIX-4 一起做。

### FIX-6【MINOR】get_entry 无条件读 staging，不受 include_pending 约束（Claude Opus m2）
- 位置：handlers.py READABLE_DIRS 含 staging，agent 没 opt-in pending 也能按 id 直读未审 pending
- 修：get_entry 也分级——默认仅 published（entries/），pending 需显式参数。与 search_kb 的 include_pending 语义一致。
- （注：这条改 get_entry 读取范围，确认不影响 Kona 正常按 id 读 published 的主路径）

### FIX-7【MINOR】sort="updated_desc" 实际按 id 排序（Claude Opus m1）
- handlers.py:349 sorted key 用 r["id"] 而非 updated 字段。要么真按 updated 排，要么改名避免语义错。

## 记 TODO（不阻塞）
- limit 无上限/类型未校验（Claude m3）→ clamp 上限
- 每次 propose 新建 IDAllocator（Claude m4）→ 复用单例（功能正确，性能优化）
- search 不支持子目录（Kimi MINOR-2，当前 flat 设计）→ 文档化或后续 rglob
- inputSchema additionalProperties 过宽（Kimi MINOR-3）→ 后续补严格 JSON Schema
- possible_duplicates（E_DUP）恒空 → 后续 Phase
- NIT：_require 里 read_published 占位、读写两套鉴权语义一致性、SearchResult.stale 是 P3 扩展加注释

## 闭环要求（R14）
1. 修完 FIX-1~7，每个补对应失败测试（尤其两个 BLOCKER 的绕过尝试 + 反转那个固化错误行为的测试）
2. 重跑三道门：ruff format/check + mypy + pytest --cov，贴真实输出
3. progress.md 记录根因总纲（id/路径先校验）+ 每个 FIX 修复思路 + TODO
4. 更新当前 PR #3 分支（不新建）
5. 逐条回报处理结果

## 特别提醒
FIX-1/FIX-2 是"id/路径未校验形状"的同源问题。修的时候建立统一防护：**所有按 id 读写的 MCP 入口，先校验 `^KB-\d{4}-\d{4}$` 再用，路径读取 resolve 后确认在白名单目录内。** 这样不只修这两个，而是堵住整类穿越/绕号漏洞。两个专项必查（复用 pipeline / research 不可见）的剩余缺口就是这两个 BLOCKER，修完 P3 才真正立住。
