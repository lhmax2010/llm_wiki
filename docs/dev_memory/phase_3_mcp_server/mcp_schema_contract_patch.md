# MCP Schema Contract Patch

Date: 2026-08-21

This follow-up patch fixes a Phase 3 MCP contract correctness bug. The stdio MCP
wrapper previously advertised every tool as an empty schema
(`additionalProperties: true`) and forwarded tool arguments directly to
handlers. That made `search_kb` filters hard for agents to discover and let
misspelled filters such as `scope={"modules": "photo"}` silently widen into an
unscoped full-KB search.

Changes:

- Added enforced schemas for all seven MCP tools.
- `tools/list` now returns the same schema used by `tools/call` validation.
- Nested schema definitions are inlined so MCP clients can show agents the real
  `search_kb.scope` shape.
- Top-level tool arguments and `search_kb.scope` use `extra="forbid"`.
- `draft`, `patch`, and `credibility` remain permissive `dict[str, Any]`
  payloads because the Governed API/P2 pipeline owns entry validation.
- Argument validation failures return JSON-RPC `-32602` (`invalid params`) with
  `data.code=E_SCHEMA`.

Scope boundary:

- This patch is separate from L2 search-index performance work.
- It does not add SQL pushdown, SQLite columns, stale detection, or index
  fallback changes.
- `scripts/profile_search.py` is a separate local performance analysis script
  and is intentionally not part of this patch.
