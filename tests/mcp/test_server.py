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


def test_tools_list_declares_real_argument_schemas(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    response = handle_jsonrpc_line(
        handlers,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name, tool in tools.items():
        schema = tool["inputSchema"]
        assert schema["additionalProperties"] is False, name
        # $defs/$ref are inlined so a client that does not resolve them still
        # shows the agent the real argument shape.
        assert "$defs" not in json.dumps(schema), name

    search = tools["search_kb"]["inputSchema"]
    assert search["required"] == ["query"]
    assert set(search["properties"]) == {
        "query",
        "scope",
        "include_pending",
        "expand_synonyms",
        "limit",
        "offset",
        "sort",
    }
    scope = search["properties"]["scope"]["anyOf"][0]
    assert scope["additionalProperties"] is False
    assert set(scope["properties"]) == {
        "module",
        "entry_type",
        "error_code",
        "claim_type",
        "min_support",
        "exclude_stale",
        "status",
    }


def test_misspelled_scope_key_is_rejected_instead_of_silently_widening(tmp_path: Path) -> None:
    """The bug this guards: scope={"modules": ...} used to return the whole KB.

    An agent doing duplicate detection reads that as "this module already has
    many similar entries", so a silent widening is worse than an error.
    """
    handlers = _handlers(tmp_path)
    for number, module in ((1, "photo"), (2, "decoder")):
        payload = entry_payload(entry_id=f"KB-2026-{number:04d}", trust_state="published")
        payload["module"] = module
        write_entry(
            handlers.kb_root / "entries" / f"KB-2026-{number:04d}.md",
            Entry.model_validate(payload),
        )

    response = _call(handlers, "search_kb", {"query": "decoder", "scope": {"modules": "photo"}})

    assert response is not None
    assert "error" in response, "misspelled scope key must not be silently ignored"
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["code"] == "E_SCHEMA"
    assert "modules" in response["error"]["message"]


def test_correct_scope_still_filters(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    for number, module in ((1, "photo"), (2, "decoder")):
        payload = entry_payload(entry_id=f"KB-2026-{number:04d}", trust_state="published")
        payload["module"] = module
        write_entry(
            handlers.kb_root / "entries" / f"KB-2026-{number:04d}.md",
            Entry.model_validate(payload),
        )

    scoped_args = {"query": "decoder", "scope": {"module": "photo"}}
    unscoped = _result(_call(handlers, "search_kb", {"query": "decoder"}))
    scoped = _result(_call(handlers, "search_kb", scoped_args))

    assert {item["id"] for item in unscoped} == {"KB-2026-0001", "KB-2026-0002"}
    assert [item["module"] for item in scoped] == ["photo"]


@pytest.mark.parametrize(
    ("arguments", "expected_in_message"),
    [
        ({"query": "x", "module": "photo"}, "module"),
        ({"query": "x", "scope": {"entry_type": "defect-case"}}, "entry_type"),
        ({"query": "x", "scope": {"min_support": "very_strong"}}, "min_support"),
        ({"query": "x", "sort": "relevance"}, "sort"),
        ({"query": "x", "limit": 5000}, "limit"),
        ({}, "query"),
    ],
)
def test_bad_search_arguments_are_rejected_with_the_offending_key(
    tmp_path: Path,
    arguments: dict[str, Any],
    expected_in_message: str,
) -> None:
    response = _call(_handlers(tmp_path), "search_kb", arguments)

    assert response is not None
    assert "error" in response
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["code"] == "E_SCHEMA"
    assert expected_in_message in response["error"]["message"]


def test_proposal_payload_dicts_stay_permissive(tmp_path: Path) -> None:
    """draft/patch/credibility belong to the Governed API pipeline, not to us.

    Locking their keys here would duplicate that contract and reject proposals
    the pipeline would have accepted, so only the tool arguments are strict.
    """
    handlers = _handlers(tmp_path)
    payload = entry_payload(entry_id=None, trust_state="pending")
    payload.pop("credibility")

    response = _call(
        handlers,
        "propose_entry",
        {
            "draft": {**payload, "some_future_field": "tolerated"},
            "credibility": {
                "claim_type": "observation",
                "support_strength": "strong",
                "evidence": [{"type": "human_note", "excerpt": "Observed by reviewer."}],
            },
            "request_id": "req-1",
        },
    )

    assert response is not None
    # It may still fail downstream validation, but not with an argument error.
    assert "error" not in response or response["error"]["data"]["code"] != "E_SCHEMA"


def _call(handlers: MCPHandlers, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    return handle_jsonrpc_line(
        handlers,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        ),
    )


def _result(response: dict[str, Any] | None) -> Any:
    assert response is not None, "no response"
    assert "error" not in response, response.get("error")
    return json.loads(response["result"]["content"][0]["text"])


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
