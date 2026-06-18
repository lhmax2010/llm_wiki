# Phase 7b 代码 Review 请求（统一知识库 · 知识图谱 + related 编辑）

## 怎么 review

代码在 workspace（分支 `phase/7b-graph`）。重点看：

- `core/validation.py` 的 related 校验 ★
- `web_api/service.py` + `web_api/app.py` 的 `GET /api/graph` ★
- `web/src/App.tsx` + `web/src/api.ts` + `web/src/types.ts` 的 related 表单和图谱 UI ★
- `tests/core/test_validation.py`
- `tests/web_api/test_app.py`
- `web/src/App.test.tsx`

设计基线：`docs/design.md`（related 字段、P7b 图谱、P2 pipeline、P7a Web 只读隔离）。

## 背景

Phase 7b 做两件配套工作：

1. Web 编辑表单支持 `related` 字段，让人能提交知识之间的关联。
2. Web 只读图谱展示 published 知识之间的 related 网络。

风险档：中-高（偏高）。写入侧碰 P8 Web propose 输入，但不动 P2/P5 核心；读侧是只读图谱，但必须继承 P7a/P6 隔离。

不做：Chat UI、research 收集 UI、P9 collector、复杂图谱交互/过滤/搜索、图数据库。

## 已通过（开发自测）

- `uv run pytest tests\core\test_validation.py -q --no-cov` -> 43 passed
- `uv run pytest tests\web_api\test_app.py -q --no-cov` -> 38 passed, 1 warning
- `npm.cmd test -- --run` -> 7 passed
- `npm.cmd run lint` -> passed
- `npm.cmd run build` -> passed

## ★ 专项 1：related 写入不绕 P8/P2

P7b 不新增 related 专用写端点；related 只作为 entry 字段进入既有：

- `POST /api/entries`
- `PATCH /api/entries/{id}`

**挖：**

- Web 层有没有新开“写 related”的文件写路径？
- related 是否仍走 P2 七段 pipeline（auth/schema/evidence/classify/review/persist/audit）？
- P8 已守住的 `X-KB-User`、`X-KB-Write-Intent`、JSON-only、严格 DTO 是否仍生效？
- payload 能不能夹带 `id/trust_state/author_type/changed_fields/target_dir/role` 绕治理？

## ★ 专项 2：related id 校验和 research 隔离

写入策略：只允许 KB-id；target 必须存在于 `entries/`、`staging/`、`deprecated/` 任一；不强制 published；自关联拒；循环允许。

**挖：**

- related 校验是否在 P1 `validate_entry()`，从而所有入口继承？
- `R-2026-0001`、`research:*`、非法 id 是否都拒？
- 存在性检查是否只查 `entries/staging/deprecated`，绝不查 `research`？
- 只存在于 `research/` 的同名/相似目标会不会被当成存在？
- 不存在 id 是否拒绝？
- `A -> A` 是否拒绝？
- `A -> B` 和 `B -> A` 是否允许？

## ★ 专项 3：图谱只读隔离

图谱端点：`GET /api/graph`。数据源应该复用 P7a/P4 published-only safe reader。

**挖：**

- 图谱是否只读，没有写入副作用？
- 是否复用 `read_valid_entries_from_source(kb_root, "entries")`？
- 有没有新写扫描 `research/staging/drafts/deprecated` 的路径？
- published entry related 到 pending/deprecated target 时，边是否不画？
- 节点是否只包含 published entries？
- research title/tag/body/id 是否能经 graph 响应泄漏？

## ★ 专项 4：图谱边语义

related 数据是有向的，但 UI 不应把 A<->B 画成两条平行线。

**挖：**

- reciprocal A<->B 是否折成一条 `bidirectional` 视觉边？
- 单向 A->B 是否仍可显示为一条边？
- 图谱是否每次读当前 published 状态，而不是旧快照？

## ★ 专项 5：前端最小可用

前端使用轻量 React/SVG，无新增 npm 图谱依赖。

**挖：**

- create/edit 都能填 related？
- related payload 是否只含 target/type/origin/note，不含治理字段？
- 图谱按钮是否调用 `/api/graph`？
- 点击节点是否走 `GET /api/entries/{id}` 打开详情，而不是前端直接读文件？
- 文本/节点是否基本可读，移动端不会明显炸布局？

## BLOCKER / MAJOR / MINOR / NIT（逐条）

请按严重程度标：

- BLOCKER：绕过 P2/P8 写入边界、图谱泄漏 research、非法 related 可进入 KB。
- MAJOR：related 校验层级不对、图谱扫描路径不安全、pending/research 在图谱可见。
- MINOR：UI 可用性、错误提示、图谱小数据布局问题。
- NIT：命名、注释、后续优化。

## 总体

给结论：可合并 / 改后可合并 / 有 BLOCKER。
