# 统一知识库（Unified Knowledge Base）

团队共享知识库：人通过 Web App 读写，agent（如 Kona）通过 MCP 读写，**同一份内容核**。

## 是什么
- 内容核（SSOT）：结构化知识 + 可信度纪律（claim_type 证据映射/段落级可信度/code_binding）
- agent 层：MCP server（6 标准工具 + 1 可选 research hints）+ skill 契约
- 人用层：Web App（浏览/编辑分级/知识图谱/CJK 搜索/Chat UI）
- research 收集层（物理隔离）+ collector 采集管线
- API-First / Headless：MCP/Web/Collector 都是 Governed API 的 client

完整设计见 `docs/design.md`（v1.2 FROZEN），开发规约见 `docs/governance.md`（R1-R14）。

## 技术栈
- 后端：Python（已冻结）
- 前端：React（Web App）
- 存储：Git + Markdown + YAML（SSOT）+ SQLite（索引+发号）
- 检索：ripgrep + 同义词表 + CJK（非 RAG，语义 V1.5）

## 开发
1. 读 `docs/design.md` + `docs/governance.md`
2. 补 P1 前置：hash 口径页、governance（已派生）
3. 按 `docs/design.md` §7 Phase DAG 逐个 Phase 开发（Codex）
4. 关键路径：P1→P2→P3→P5→P6→P8→P9；P1-P5+P10a 后 Kona 可接入

## 目录
```
docs/          设计+规约+开发过程留痕
core/          内容核（schema+校验+存储）
governed-api/  治理 middleware pipeline
mcp/           MCP server（agent 层）
web/           Web App（人用层）
collector/     采集管线
index/         索引（grep+同义词+CJK）
config/        roles.yaml（RBAC）
kb/            内容核运行时数据（git 仓库）
  entries/ staging/ drafts/ research/ deprecated/
  attachments/{public,private}/ indexes/ skills/
scripts/       索引生成/渲染/健康检查
```

## ⚠️ 注意
内网项目，含同事数据/缺陷单/可能客户信息，不进任何公网。
