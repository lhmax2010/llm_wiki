from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from governed_api.roles import RolesConfig

from core.models import Entry
from core.storage import write_entry
from mcp.kb_server.handlers import MCPHandlers
from mcp.kb_server.server import handle_jsonrpc_line, run_stdio_server
from tests.governed_api.helpers import entry_payload


def test_tools_list_exposes_phase_3_tools(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    response = handle_jsonrpc_line(
        handlers,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )

    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {
        "search_kb",
        "get_entry",
        "list_categories",
        "browse",
        "propose_entry",
        "propose_update",
        "search_research_for_hints",
    }


def test_tools_call_invokes_handler_and_returns_text_json(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    write_entry(handlers.kb_root / "entries" / "KB-2026-0001.md", Entry.model_validate(payload))
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "get_entry", "arguments": {"id": "KB-2026-0001"}},
    }

    response = handle_jsonrpc_line(handlers, json.dumps(request))

    assert response is not None
    text = response["result"]["content"][0]["text"]
    assert json.loads(text)["id"] == "KB-2026-0001"


def test_stdio_server_loop_handles_list_and_call(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    write_entry(handlers.kb_root / "entries" / "KB-2026-0001.md", Entry.model_validate(payload))
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "search_kb",
                            "arguments": {"query": "decoder"},
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    run_stdio_server(handlers, stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["result"]["tools"][0]["name"] == "search_kb"
    search_payload = json.loads(responses[1]["result"]["content"][0]["text"])
    assert search_payload[0]["id"] == "KB-2026-0001"


def test_invalid_json_returns_parse_error_and_loop_continues(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    stdin = StringIO(
        "{bad json}\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    )
    stdout = StringIO()

    run_stdio_server(handlers, stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == -32700
    assert responses[1]["result"]["tools"][0]["name"] == "search_kb"


def test_unexpected_tool_exception_returns_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(self: MCPHandlers, **kwargs: Any) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(MCPHandlers, "search_kb", boom)
    handlers = _handlers(tmp_path)
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "search_kb", "arguments": {"query": "decoder"}},
    }

    response = handle_jsonrpc_line(handlers, json.dumps(request))

    assert response is not None
    assert response["error"]["code"] == -32603


def _handlers(tmp_path: Path) -> MCPHandlers:
    return MCPHandlers(
        repo_root=tmp_path,
        kb_root=tmp_path / "kb",
        roles_config=RolesConfig(
            roles={"contributor": ["read_published", "propose_entry"]},
            users={"alice": "contributor"},
        ),
        user="alice",
    )
