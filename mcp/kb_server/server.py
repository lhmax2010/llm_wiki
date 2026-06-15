"""Minimal JSON-RPC stdio wrapper for the Phase 3 MCP tools."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from governed_api.roles import load_roles_config

from core.id_allocator import IDAllocator
from mcp.kb_server.handlers import MCPHandlers, ToolError
from mcp.kb_server.types import ToolCallResult, ToolDescriptor

LOGGER = logging.getLogger(__name__)


def tool_descriptors() -> list[ToolDescriptor]:
    return [
        _tool("search_kb", "Search published KB entries."),
        _tool("get_entry", "Get one KB entry by id."),
        _tool("list_categories", "List modules, entry types, tags, and error codes."),
        _tool("browse", "Browse entries by module and optional entry type."),
        _tool("propose_entry", "Propose a new KB entry through the Governed API pipeline."),
        _tool("propose_update", "Propose an update through the Governed API pipeline."),
        _tool("search_research_for_hints", "Return opt-in research hints; P3 stub returns none."),
    ]


def run_stdio_server(
    handlers: MCPHandlers, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout
) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            response = handle_jsonrpc_line(handlers, line)
        except Exception as exc:
            LOGGER.exception("MCP stdio loop recovered from unhandled error")
            response = _error_response(None, -32603, f"internal error: {type(exc).__name__}")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def handle_jsonrpc_line(handlers: MCPHandlers, line: str) -> dict[str, Any] | None:
    request_id: object | None = None
    try:
        request = json.loads(line)
        if not isinstance(request, dict):
            return _error_response(request_id, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        result: dict[str, Any] | ToolCallResult
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "unified-kb", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": tool_descriptors()}
        elif method == "tools/call":
            result = _call_tool(handlers, params)
        elif method == "notifications/initialized":
            return None
        else:
            return _error_response(request_id, -32601, f"method not found: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except json.JSONDecodeError as exc:
        return _error_response(request_id, -32700, f"parse error: {exc.msg}")
    except ToolError as exc:
        return _error_response(request_id, -32000, exc.message, exc.to_dict())
    except (TypeError, ValueError, KeyError) as exc:
        return _error_response(request_id, -32602, str(exc))
    except Exception as exc:
        LOGGER.exception("MCP tool call failed with internal error")
        return _error_response(request_id, -32603, f"internal error: {type(exc).__name__}")


def build_handlers(repo_root: Path, *, user: str) -> MCPHandlers:
    kb_root = repo_root / "kb"
    return MCPHandlers(
        repo_root=repo_root,
        kb_root=kb_root,
        roles_config=load_roles_config(repo_root / "config" / "roles.yaml"),
        user=user,
        id_allocator=IDAllocator(kb_root / "indexes" / "ids.sqlite"),
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    repo_root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    user = argv[1] if len(argv) > 1 else "kona-agent"
    run_stdio_server(build_handlers(repo_root, user=user))
    return 0


def _call_tool(handlers: MCPHandlers, params: dict[str, Any]) -> ToolCallResult:
    name = params["name"]
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    dispatch: dict[str, Callable[..., object]] = {
        "search_kb": handlers.search_kb,
        "get_entry": handlers.get_entry,
        "list_categories": handlers.list_categories,
        "browse": handlers.browse,
        "propose_entry": handlers.propose_entry,
        "propose_update": handlers.propose_update,
        "search_research_for_hints": handlers.search_research_for_hints,
    }
    if name not in dispatch:
        raise ToolError("E_SCHEMA", f"unknown tool: {name}", "name")
    payload = dispatch[name](**arguments)
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _tool(name: str, description: str) -> ToolDescriptor:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "additionalProperties": True},
    }


def _error_response(
    request_id: object,
    code: int,
    message: str,
    data: object | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


if __name__ == "__main__":
    raise SystemExit(main())
