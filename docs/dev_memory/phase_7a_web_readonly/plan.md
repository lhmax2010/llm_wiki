# Phase 7a - Web Readonly / Plan

## 目标

实现最小可用的人读 Web：只读 HTTP API + React 前端，支持条目搜索、列表/浏览、详情查看。P7a 只消费既有内容核和 P4 human search，不新增任何写入路径。

## 范围

### HTTP API

- 暴露只读端点：
  - `GET /api/entries`：搜索/列表，复用 `SearchService.search_human()` 和 `human_search_index`。
  - `GET /api/entries/{id}`：返回完整结构化 JSON；前端负责隐藏技术字段。
  - `GET /api/categories`：模块、entry_type、tag、error_code 聚合。
  - `GET /api/browse`：按 `module` + 可选 `entry_type` 浏览 published 条目。
- 框架候选：FastAPI。design 只规定 Python 后端，没有锁定 FastAPI/Flask；FastAPI 与 Pydantic/TypedDict 边界更贴合，并自带 OpenAPI 与测试客户端。编码前如需新增依赖，按 R8 单独报批。
- 不暴露 `POST`/`PUT`/`PATCH`/`DELETE`，不暴露 propose/review/research/collector 端点。

### 安全边界

- 只读：P7a HTTP app 不注册任何写入路由。
- research 物理不可见：HTTP search 使用 P4 的 `human_search_index`，该 index 的 `source_dirs=("entries",)`，不含 `research/`；fallback 如需实现，也必须复用 P4 的安全读路径且只扫 `entries/`。
- `get_entry` ID 必须校验 `^KB-\d{4}-\d{4}$`，并复用 P3/P4 已验证的 resolve/is_relative_to 读路径纪律，禁止路径拼接绕过。
- query/scope/limit/offset/sort 做输入校验；检索层继续使用 P4 的参数化 Python API，不拼 SQL，不接受任意路径或目录参数。
- 后端返回完整 JSON，前端隐藏 frontmatter/技术字段是视图选择，不是后端裁剪安全模型。

### React 前端

- 最小视图：
  - 搜索框。
  - 结果列表。
  - 条目详情页/详情面板。
- 前端通过 HTTP API 读取，不直接读文件。
- 人读视图隐藏 frontmatter 和内部技术字段；保留可信度摘要、证据摘要、stale 状态等人可理解信息。
- 不做编辑、图谱、Chat/NL search、复杂过滤、排序、分页、登录/session。

## 明确不做

- 不做 Phase 7b 图谱或 Chat UI。
- 不做 Phase 8 编辑、research UI、review UI。
- 不做 collector、Web 写入、approve/reject、propose/promote 端点。
- 不改 P1-P6 核心治理、存储、索引、research 隔离逻辑。

## 计划步骤

1. 确认后端框架与前端工具链依赖，必要时按 R8 报批。
2. 建 HTTP API 包，接入 `SearchService.search_human()` 与安全的 entry/category/browse 读取服务。
3. 补 API 单测：只读路由、research 不可见、ID traversal 拒绝、scope/query 校验、返回完整 JSON。
4. 建 React 最小 app，搜索/列表/详情通过 HTTP API 获取数据。
5. 补前端测试：搜索渲染、详情隐藏技术字段、空态/错误态。
6. 写 P7a review prompt，专项检查只读边界、research 隔离、ID/参数校验、前端不直读文件。
7. 跑 R13：ruff format/check、mypy、pytest --cov、npm lint/test、Web 本机集成验收。

## 依赖

- Phase 4：`human_search_index` 和 `SearchService.search_human()`。
- Phase 3/4：按 id 读取条目的形状校验、路径白名单、坏文件容错纪律。
- Phase 6：research 物理隔离；P7a 不把 research 纳入人读主搜索。
- 待确认依赖：HTTP 框架、React/Vite/Vitest/Testing Library 等前端工具链。

## DoD

- HTTP API 只注册只读端点，测试证明没有写入端点。
- `/api/entries` 使用 human search，CJK 查询可命中，且 research 内容搜不到。
- `/api/entries/{id}` 拒绝非法 id/path traversal，合法 id 返回完整结构化 JSON。
- `list_categories`/`browse` 只读 published entries，不含 research。
- React 首页可搜索并打开详情；详情人读视图隐藏 frontmatter/内部技术字段。
- Python 三道门通过，前端 lint/test 通过，本机 Web 集成验收通过。

## 风险档初判

Phase 7a 初判为普通风险，建议两路 review（Claude + ChatGPT）。

理由：P7a 是只读 Web，不新增写入/propose/review/research 路径，不改 P1-P6 核心纪律；主要风险来自 HTTP API 作为新读入口可能泄漏 research 或重新打开 id/path/query 校验缺口。用只读路由白名单、human index 源头排除 research、ID 形状校验与 P4 安全读路径、API/前端专项测试控制。

## Baseline

- 分支：`phase/7a-web-readonly`
- baseline commit：`5e77476bd6b6c79cc9a882cab945b44cbb7bd2d7`
