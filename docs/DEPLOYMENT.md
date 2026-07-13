# Unified KB 独立部署指南

本文说明如何在另一台机器上完整部署 unified-kb，使 Web 前端、HTTP API、KB 本地数据、Review UI、Graph UI，以及可选的 Cline MCP 接入都运行在同一台机器上，不依赖开发机。

当前项目是内网 MVP：

- Web 后端是 FastAPI，默认端口 `8000`。
- Web 前端是 Vite/React，默认通过 `/api/*` 代理到 `127.0.0.1:8000`。
- MCP 是本地 stdio wrapper，不是 HTTP 服务；由 Cline 等 MCP client 按配置启动。
- `X-KB-User` 是内网信任头，不是真登录系统。不要直接暴露到公网。

## 1. 准备环境

部署机需要：

- Python `>=3.11`
- `uv`
- Node.js + npm
- git

拉取代码：

```powershell
git clone https://github.com/lhmax2010/llm_wiki.git
cd llm_wiki\unified-kb
git switch main
git pull --ff-only
```

如果部署机不能访问 GitHub，就从开发机拷贝 repo 压缩包或 git bundle 到部署机。

## 2. 安装依赖

Python 依赖：

```powershell
cd C:\path\to\llm_wiki\unified-kb
uv sync --system-certs
```

前端依赖：

```powershell
cd C:\path\to\llm_wiki\unified-kb\web
npm install
# After pulling PR #15 or later, run npm install again so d3-force is present.
```

企业网络如果有 SSL 拦截，优先使用系统证书配置；Node/npm 侧按本机企业网络策略配置 registry/cert。

## 3. 配置本地用户权限

Web 后端支持通过环境变量指定本地 roles 文件。建议创建部署机本地文件：

`C:\path\to\llm_wiki\unified-kb\config.local.roles.yaml`

```yaml
roles:
  reader:
    - read_published
  contributor:
    - read_published
    - create_research
    - edit_own_research
    - propose_entry
    - promote_research_to_draft
  reviewer:
    - read_published
    - create_research
    - edit_own_research
    - propose_entry
    - promote_research_to_draft
    - read_research
    - read_draft
    - review_light
    - review_heavy
    - publish_entry
    - deprecate_entry
    - manage_tags
    - search_research_for_hints
  admin:
    - "*"

users:
  cline-test: contributor
  reviewer1: reviewer
```

Web UI 中：

- 新建/编辑知识：`User = cline-test`
- 审核 approve/reject：`User = reviewer1`

`config.local.*` 已被 `.gitignore` 忽略。不要把真实人员映射提交到公网 repo。

## 4. 准备本地 KB 数据

干净测试环境只需要目录存在：

```powershell
cd C:\path\to\llm_wiki\unified-kb
New-Item -ItemType Directory -Force kb\entries,kb\staging,kb\deprecated,kb\indexes,kb\research,kb\drafts
```

如果要迁移真实 KB，把真实的 `kb/entries/*.md`、`kb/staging/*.md`、`kb/indexes/*.jsonl` 等复制到部署机本地。不要依赖开发机路径或网络共享。

建议在部署机本地确认这些运行数据不会被提交：

```text
# .git/info/exclude
kb/staging/*.md
kb/entries/*.md
kb/deprecated/*.md
kb/indexes/*.jsonl
kb/indexes/**/*.sqlite
config.local.*
```

注意：`kb/skills/*.md` 是共享行为契约，应保留为 tracked 文件；不要把它和真实知识数据混在一起忽略。

## 5. 重建索引

迁移了 entries/research 后建议重建一次索引：

```powershell
cd C:\path\to\llm_wiki\unified-kb
uv run python scripts/rebuild_indexes.py --kb-root kb
```

即使不重建，HTTP/MCP search 仍有安全 fallback；但正式迁移数据后重建会让索引状态更清晰。

## 6. 启动 HTTP 后端

新开一个终端：

```powershell
cd C:\path\to\llm_wiki\unified-kb
$env:UNIFIED_KB_REPO_ROOT=(Resolve-Path .).Path
$env:UNIFIED_KB_ROOT="kb"
$env:UNIFIED_KB_ROLES=(Resolve-Path .\config.local.roles.yaml).Path
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"

uv run uvicorn web_api.app:app --host 127.0.0.1 --port 8000
```

后端 API 包括：

- `GET /api/entries`
- `GET /api/entries/{id}`
- `GET /api/categories`
- `GET /api/browse`
- `GET /api/graph`
- `POST /api/entries`
- `PATCH /api/entries/{id}`
- `GET /api/review/queue`
- `POST /api/review/{entry_id}/approve`
- `POST /api/review/{entry_id}/reject`

## 7. 启动 Web 前端

另开一个终端：

```powershell
cd C:\path\to\llm_wiki\unified-kb\web
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

访问：

```text
http://127.0.0.1:5174
```

前端通过 `/api/*` 代理到后端 `127.0.0.1:8000`。改后端代码、前端代码、Vite proxy 配置或拉取新版本后，重启后端和前端，避免旧进程保留旧 route/proxy。

## 8. 验证 Web

直接测后端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/categories
Invoke-RestMethod -Headers @{"X-KB-User"="reviewer1"} http://127.0.0.1:8000/api/review/queue
```

在浏览器中：

1. 打开 `http://127.0.0.1:5174`。
2. `User` 填 `cline-test`，新建一条知识，应该进入 `kb/staging/`。
3. `User` 填 `reviewer1`，打开 Review，应该能看到待审条目。
4. approve 后，条目应从 `kb/staging/` 进入 `kb/entries/`。
5. 普通 Search 默认只搜索 published entries；pending 条目在 Review 队列中看。

## 9. 可选：配置 Cline MCP

MCP 是本地 stdio，不需要常驻端口。Cline 配置示例：

```json
{
  "mcpServers": {
    "unified-kb": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "mcp.kb_server.server",
        "C:/path/to/llm_wiki/unified-kb",
        "cline-test"
      ],
      "cwd": "C:/path/to/llm_wiki/unified-kb",
      "env": {
        "PYTHONPATH": "C:/path/to/llm_wiki/unified-kb/governed-api",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      },
      "disabled": false
    }
  }
}
```

当前 MCP server 固定读取 `config/roles.yaml`，不读取 `UNIFIED_KB_ROLES`。因此如果要让 Cline MCP 用 `cline-test` propose，需要在部署机本地的 `config/roles.yaml` 中加入用户映射，例如：

```yaml
users:
  cline-test: contributor
```

这是部署机本地配置，不要提交真实人员映射。如果部署机也用于开发提交，修改前先确认不会把本地 `config/roles.yaml` 推回公网。

## 10. 让 Cline 使用白话沉淀 skill

Cline 不会自动加载 `kb/skills/*.md`。在 Cline Custom Instructions 或项目 `.clinerules` 中加入：

```text
使用统一知识库时，先读取并遵守：
- kb/skills/ingest_skill.md
- kb/skills/whisper_ingest_skill.md

只能通过 MCP 工具 search_kb/get_entry/propose_entry/propose_update 写入。
白话沉淀必须先起草给人确认，确认后才 propose。
```

`whisper_ingest_skill.md` 负责白话理解、原话留底、起草后人确认；`ingest_skill.md` 负责查重、结构化、证据纪律和 MCP propose。

## 11. 常用地址和身份

```text
Web:      http://127.0.0.1:5174
API:      http://127.0.0.1:8000
Search:   Web 页面默认搜索 published entries
Review:   Web 页面中填 reviewer1 后打开 Review
Graph:    Web 页面中的 Graph/图谱入口
MCP:      由 Cline 按 stdio 配置自动启动，无 HTTP 端口
```

建议先只绑定 `127.0.0.1` 本机测试。若要开放给局域网，必须先补真实认证、权限边界和网络访问控制。
