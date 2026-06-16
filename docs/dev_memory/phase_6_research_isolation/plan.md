# Phase 6 - Research Isolation / Plan

## 目标

把前序 Phase 预留的 research 线补齐：`kb/research/` 作为物理隔离的未验证线索区，agent 主搜索默认完全不可见；只有显式 opt-in 的 `search_research_for_hints` 能拿到提示信号；research 可以被人工 promote 成 draft，但不能直接变成正式知识，不能被当作 evidence。

## 范围边界

做：
- 填 P3 stub：`search_research_for_hints` 返回真实 `research_signals`。
- 填 P4 placeholder：实例化独立的 `research_search_index`，只扫描 `kb/research/`。
- 新增 research store：create/update/promote/TTL report。
- 新增 promote：research 复制为新的 draft，research 原件保留，draft 后续仍走正常 review/publish。
- 新增 research evidence 禁用：P1 `validate_entry()` 拒绝 entry/section evidence 引用 research。
- 补 agent 写 research 阻断：P2 auth_context + ResearchStore 双层防护。

不做：
- 不做 Web research UI（P7/P8）。
- 不做 collector 自动采集（P9）。
- 不做 P10b Kona/Cline 端到端验收。
- 不让 research 直接进入 staging/entries。
- 不改 P1-P5 已有核心隔离逻辑，只填 research 这条线。

## 计划步骤

1. 阅读 P3/P4/P5 的预留接口和 dev_memory，确认 `search_research_for_hints`、`research_index`、review/promote 纪律。
2. 实现 `research/` 包：ResearchRecord、ResearchIdAllocator、ResearchStore、TTL report、safe read/write。
3. 实例化 `ResearchSearchIndex`，复用 P4 路径防护原则，保持与 agent/human index 独立。
4. 接入 MCP `search_research_for_hints`，返回 signal + warning，不返回完整 body/evidence。
5. 接入 P1/P2 防护：research evidence 禁用、agent author_type 写 research 阻断。
6. 实现 promote research -> draft：新 KB id、原子写 draft、validate_entry 复核、audit、duplicate/lock 防护，research 原件保留。
7. 补测试：research opt-in、主搜索隔离、index symlink 防护、promote、agent 阻断、TTL、不允许 research evidence。
8. 写 review prompt，跑 R13 三道门。

## 依赖

- P1 content core：Entry schema、storage、validate_entry、E_RESEARCH_AS_EVIDENCE。
- P2 Governed API：RBAC、audit、auth_context。
- P3 MCP：`search_research_for_hints` stub。
- P4 index/search：source root 白名单、symlink/坏文件跳过、SearchService。
- P5 review discipline：状态搬运的原子写、校验、audit、锁/重复防护经验。

## 风险档

高风险，三路 review（Claude + ChatGPT + Kimi）。

专项必查：
- agent 主搜索/agent index 物理不含 research。
- `search_research_for_hints` 必须显式 opt-in 且只返回 signal。
- promote 不能绕过 review，必须生成 draft 且保留 research 原件。
- agent 不能 create/update/promote research。
- research 不能作为 entry/section evidence。

## Baseline

- branch: `phase/6-research-isolation`
- baseline commit: `ff15cf146abf4226e0a5d0210b668dcbcca3eb57`
