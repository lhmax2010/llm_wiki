from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from governed_api.roles import RolesConfig
from governed_api.types import MiddlewareContext, MiddlewareResult, ok

from core.id_allocator import IDAllocator
from core.models import Entry
from core.storage import write_entry
from mcp.kb_server.handlers import MCPHandlers, ToolError
from tests.governed_api.helpers import body_for, entry_payload


@pytest.fixture
def roles_config() -> RolesConfig:
    return RolesConfig(
        roles={
            "reader": ["read_published"],
            "contributor": ["read_published", "propose_entry"],
            "reviewer": ["read_published", "propose_entry", "search_research_for_hints"],
        },
        users={"alice": "contributor", "reader": "reader", "reviewer": "reviewer"},
    )


@pytest.fixture
def handlers(tmp_path: Path, roles_config: RolesConfig) -> MCPHandlers:
    kb_root = tmp_path / "kb"
    return MCPHandlers(
        repo_root=tmp_path,
        kb_root=kb_root,
        roles_config=roles_config,
        user="alice",
        id_allocator=IDAllocator(kb_root / "indexes" / "ids.sqlite"),
    )


def test_search_kb_uses_directory_whitelist_and_pending_means_staging_only(
    handlers: MCPHandlers,
) -> None:
    _write_entry(handlers.kb_root / "entries" / "KB-2026-0001.md", trust_state="published")
    _write_entry(
        handlers.kb_root / "staging" / "KB-2026-0002.md",
        entry_id="KB-2026-0002",
        trust_state="pending",
        title="Pending decoder failure",
    )
    _write_entry(
        handlers.kb_root / "drafts" / "KB-2026-0003.md",
        entry_id="KB-2026-0003",
        trust_state="draft",
        title="Draft decoder failure",
    )
    _write_entry(
        handlers.kb_root / "research" / "KB-2026-0004.md",
        entry_id="KB-2026-0004",
        trust_state="research",
        title="Research decoder failure",
    )

    published_only = handlers.search_kb("decoder")
    with_pending = handlers.search_kb("decoder", include_pending=True)

    assert [result["id"] for result in published_only] == ["KB-2026-0001"]
    assert {result["id"] for result in with_pending} == {"KB-2026-0001", "KB-2026-0002"}
    assert "KB-2026-0003" not in {result["id"] for result in with_pending}
    assert "KB-2026-0004" not in {result["id"] for result in with_pending}


def test_search_kb_support_scope_can_match_section(handlers: MCPHandlers) -> None:
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["credibility"]["support_strength"] = "weak"
    payload["section_credibility"] = {
        "Root Cause": {"claim_type": "fact", "support_strength": "strong", "evidence": []}
    }
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", payload)

    results = handlers.search_kb("decoder", scope={"min_support": "strong"})

    assert len(results) == 1
    assert results[0]["matched_section"] == "Root Cause"


def test_get_entry_returns_complete_agent_view(handlers: MCPHandlers) -> None:
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["section_credibility"] = {
        "Evidence": {
            "claim_type": "observation",
            "support_strength": "strong",
            "evidence": [{"type": "human_note", "excerpt": "Section observation."}],
        }
    }
    payload["code_binding"] = {
        "repo_id": "kona",
        "paths": ["decoder/foo.c"],
        "path_hashes": {"decoder/foo.c": "a" * 64},
        "symbol_resolution": "fallback_path",
        "stale": True,
        "stale_reason": "path changed",
    }
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", payload)

    result = handlers.get_entry(id="KB-2026-0001")

    assert result["credibility"]["claim_type"] == "observation"
    assert result["credibility"]["support_strength"] == "strong"
    assert result["credibility"]["evidence"][0]["type"] == "human_note"
    assert result["section_credibility"]["Evidence"]["support_strength"] == "strong"
    assert result["code_binding"]["paths"] == ["decoder/foo.c"]
    assert result["code_binding"]["stale"] is True
    assert result["code_binding"]["stale_reason"] == "path changed"


def test_list_categories_and_browse_read_published_entries_only(handlers: MCPHandlers) -> None:
    _write_entry(
        handlers.kb_root / "entries" / "KB-2026-0001.md",
        trust_state="published",
        tags=["decoder"],
    )
    _write_entry(
        handlers.kb_root / "staging" / "KB-2026-0002.md",
        entry_id="KB-2026-0002",
        trust_state="pending",
        title="Pending decoder failure",
        tags=["pending"],
    )

    categories = handlers.list_categories()
    browse = handlers.browse(module="decoder", entry_type="defect_case")

    assert categories["modules"] == ["decoder"]
    assert categories["tags"] == ["decoder"]
    assert [entry["id"] for entry in browse["entries"]] == ["KB-2026-0001"]


def test_propose_entry_runs_all_pipeline_steps_in_order(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    calls: list[int] = []

    def step(number: int) -> Callable[[MiddlewareContext], MiddlewareResult]:
        def _step(context: MiddlewareContext) -> MiddlewareResult:
            calls.append(number)
            next_context = context.copy()
            if number == 6:
                next_context["allocated_id"] = "KB-2026-0001"
                next_context["target_dir"] = "staging"
            return ok(next_context)

        return _step

    handlers = MCPHandlers(
        repo_root=tmp_path,
        kb_root=tmp_path / "kb",
        roles_config=roles_config,
        user="alice",
        pipeline_steps=(step(1), step(2), step(3), step(4), step(5), step(6), step(7)),
    )

    result = handlers.propose_entry(
        draft=entry_payload(entry_id=None, trust_state="pending", evidence=[]),
        credibility={"claim_type": "observation", "support_strength": "strong", "evidence": []},
        request_id="req-1",
    )

    assert calls == [1, 2, 3, 4, 5, 6, 7]
    assert result["proposed_id"] == "KB-2026-0001"
    assert result["status"] == "pending"


def test_propose_entry_uses_governed_pipeline_to_allocate_persist_and_audit(
    handlers: MCPHandlers,
) -> None:
    draft = entry_payload(entry_id=None, trust_state="pending")
    credibility = draft.pop("credibility")

    result = handlers.propose_entry(draft=draft, credibility=credibility, request_id="req-1")

    assert result["proposed_id"] == "KB-2026-0001"
    assert result["status"] == "pending"
    assert (handlers.kb_root / "staging" / "KB-2026-0001.md").exists()
    assert (handlers.kb_root / "indexes" / "audit.jsonl").exists()


def test_propose_update_uses_previous_entry_for_actual_diff_not_self_report(
    handlers: MCPHandlers,
) -> None:
    _write_entry(handlers.kb_root / "entries" / "KB-2026-0001.md", trust_state="published")

    result = handlers.propose_update(
        id="KB-2026-0001",
        patch={
            "body": body_for().replace("现象 content.", "Updated symptom."),
            "changed_fields": ["tags"],
            "change_scopes": ["typo"],
        },
        reason="agent update",
        request_id="req-2",
    )

    assert result["status"] == "pending"
    assert (handlers.kb_root / "staging" / "KB-2026-0001.md").exists()
    staged = Entry.model_validate(handlers.get_entry(id="KB-2026-0001"))
    assert staged.id == "KB-2026-0001"


def test_propose_update_without_previous_entry_can_still_run_as_heavy(
    handlers: MCPHandlers,
) -> None:
    full_patch = entry_payload(entry_id="KB-2026-0099", trust_state="published")

    result = handlers.propose_update(
        id="KB-2026-0099",
        patch=full_patch,
        reason="backfill",
        request_id="req-3",
    )

    assert result["status"] == "pending"
    assert (handlers.kb_root / "staging" / "KB-2026-0099.md").exists()


def test_research_hints_is_permissioned_stub(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    reviewer = MCPHandlers(
        repo_root=tmp_path,
        kb_root=tmp_path / "kb",
        roles_config=roles_config,
        user="reviewer",
    )
    reader = MCPHandlers(
        repo_root=tmp_path,
        kb_root=tmp_path / "kb",
        roles_config=roles_config,
        user="reader",
    )

    assert reviewer.search_research_for_hints("decoder") == {"research_signals": []}
    with pytest.raises(ToolError) as exc_info:
        reader.search_research_for_hints("decoder")
    assert exc_info.value.code == "E_PERM"


def _write_entry(
    path: Path,
    *,
    entry_id: str = "KB-2026-0001",
    trust_state: str,
    title: str = "Decoder failure",
    tags: list[str] | None = None,
) -> None:
    payload = entry_payload(entry_id=entry_id, trust_state=trust_state, tags=tags)
    payload["title"] = title
    _write_payload(path, payload)


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    write_entry(path, Entry.model_validate(payload))
