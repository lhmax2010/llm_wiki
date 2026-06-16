from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from governed_api.roles import RolesConfig
from governed_api.types import MiddlewareContext, MiddlewareResult, ok

from core.id_allocator import IDAllocator
from core.models import Entry
from core.storage import write_entry
from index.search import SearchService
from mcp.kb_server.handlers import MCPHandlers, ToolError
from research.store import ResearchRecord, write_research_record
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
        "根因": {"claim_type": "fact", "support_strength": "strong", "evidence": []}
    }
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", payload)

    results = handlers.search_kb("decoder", scope={"min_support": "strong"})

    assert len(results) == 1
    assert results[0]["matched_section"] == "根因"


def test_get_entry_returns_complete_agent_view(handlers: MCPHandlers) -> None:
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["section_credibility"] = {
        "现象": {
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
    assert result["section_credibility"]["现象"]["support_strength"] == "strong"
    assert result["code_binding"]["paths"] == ["decoder/foo.c"]
    assert result["code_binding"]["stale"] is True
    assert result["code_binding"]["stale_reason"] == "path changed"


def test_get_entry_rejects_path_traversal_and_cannot_read_research(
    handlers: MCPHandlers,
) -> None:
    _write_entry(
        handlers.kb_root / "research" / "KB-2026-0004.md",
        entry_id="KB-2026-0004",
        trust_state="research",
        title="Research-only decoder note",
    )

    with pytest.raises(ToolError) as traversal:
        handlers.get_entry(id="../research/KB-2026-0004")

    assert traversal.value.code == "E_SCHEMA"
    assert traversal.value.field == "id"
    with pytest.raises(ToolError):
        handlers.get_entry(id="KB-2026-0004", include_pending=True)


def test_get_entry_include_pending_controls_staging_visibility(handlers: MCPHandlers) -> None:
    _write_entry(
        handlers.kb_root / "staging" / "KB-2026-0002.md",
        entry_id="KB-2026-0002",
        trust_state="pending",
        title="Pending decoder failure",
    )

    with pytest.raises(ToolError):
        handlers.get_entry(id="KB-2026-0002")

    assert handlers.get_entry(id="KB-2026-0002", include_pending=True)["id"] == "KB-2026-0002"


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


def test_read_tools_skip_bad_markdown_and_log_warning(
    handlers: MCPHandlers,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _write_entry(handlers.kb_root / "entries" / "KB-2026-0001.md", trust_state="published")
    bad_path = handlers.kb_root / "entries" / "KB-2026-9999.md"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("not frontmatter", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="mcp.kb_server.handlers")

    results = handlers.search_kb("decoder")
    categories = handlers.list_categories()
    browse = handlers.browse(module="decoder")

    assert [result["id"] for result in results] == ["KB-2026-0001"]
    assert categories["modules"] == ["decoder"]
    assert [entry["id"] for entry in browse["entries"]] == ["KB-2026-0001"]
    assert "skipping unreadable entry file" in caplog.text
    assert str(bad_path) in caplog.text


def test_search_updated_desc_sorts_by_updated_timestamp(handlers: MCPHandlers) -> None:
    older = entry_payload(entry_id="KB-2026-9999", trust_state="published")
    older["title"] = "Older decoder failure"
    older["updated"] = "2026-01-01T00:00:00Z"
    newer = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    newer["title"] = "Newer decoder failure"
    newer["updated"] = "2026-12-31T00:00:00Z"
    _write_payload(handlers.kb_root / "entries" / "KB-2026-9999.md", older)
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", newer)

    results = handlers.search_kb("decoder", sort="updated_desc")

    assert [result["id"] for result in results] == ["KB-2026-0001", "KB-2026-9999"]


def test_search_kb_uses_phase4_index_for_synonym_expansion(handlers: MCPHandlers) -> None:
    (handlers.kb_root / "synonyms.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (handlers.kb_root / "synonyms.jsonl").write_text(
        '{"canonical": "花屏", "synonyms": ["绿屏", "画面错乱"]}\n',
        encoding="utf-8",
    )
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["title"] = "花屏 defect case"
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", payload)
    SearchService(handlers.kb_root).rebuild_agent_index()

    results = handlers.search_kb("绿屏")

    assert [result["id"] for result in results] == ["KB-2026-0001"]
    assert {
        "id",
        "title",
        "entry_type",
        "module",
        "snippet",
        "matched_section",
        "credibility",
        "trust_state",
        "stale",
        "score",
    }.issubset(results[0])


def test_search_kb_fallback_reuses_synonym_and_cjk_matching(handlers: MCPHandlers) -> None:
    (handlers.kb_root / "synonyms.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (handlers.kb_root / "synonyms.jsonl").write_text(
        '{"canonical": "花屏", "synonyms": ["绿屏", "画面错乱"]}\n',
        encoding="utf-8",
    )
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["title"] = "花屏 defect case"
    payload["body"] = body_for().replace("现象 content.", "画面出现绿屏。")
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", payload)

    synonym_results = handlers.search_kb("绿屏")
    cjk_results = handlers.search_kb("画面绿屏", expand_synonyms=False)

    assert [result["id"] for result in synonym_results] == ["KB-2026-0001"]
    assert [result["id"] for result in cjk_results] == ["KB-2026-0001"]


def test_search_kb_fallback_skips_entry_with_wrong_trust_state(handlers: MCPHandlers) -> None:
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="research")
    payload["title"] = "wrong-state-token"
    _write_payload(handlers.kb_root / "entries" / "KB-2026-0001.md", payload)

    assert handlers.search_kb("wrong-state-token") == []


def test_search_kb_index_mode_keeps_pending_overlay_to_staging_only(
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
        handlers.kb_root / "research" / "KB-2026-0003.md",
        entry_id="KB-2026-0003",
        trust_state="research",
        title="Research decoder failure",
    )
    SearchService(handlers.kb_root).rebuild_agent_index()

    results = handlers.search_kb("decoder", include_pending=True)

    assert {result["id"] for result in results} == {"KB-2026-0001", "KB-2026-0002"}


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


def test_propose_update_without_previous_entry_fails_and_ignores_patch_id(
    handlers: MCPHandlers,
) -> None:
    full_patch = entry_payload(entry_id="KB-2026-0001", trust_state="published")

    result = handlers.propose_update(
        id="KB-2026-0099",
        patch=full_patch,
        reason="backfill",
        request_id="req-3",
    )

    assert "status" not in result
    assert result["validation_errors"][0]["code"] == "E_SCHEMA"
    assert result["validation_errors"][0]["field"] == "id"
    assert result["validation_errors"][0]["message"] == "entry not found: KB-2026-0099"
    assert not (handlers.kb_root / "staging" / "KB-2026-0099.md").exists()
    assert not (handlers.kb_root / "staging" / "KB-2026-0001.md").exists()


def test_propose_update_rejects_invalid_id_before_path_use(handlers: MCPHandlers) -> None:
    result = handlers.propose_update(
        id="../research/KB-2026-0004",
        patch=entry_payload(entry_id="KB-2026-0004", trust_state="published"),
        reason="path traversal",
        request_id="req-4",
    )

    assert result["validation_errors"][0]["code"] == "E_SCHEMA"
    assert result["validation_errors"][0]["field"] == "id"


def test_research_hints_is_permissioned_opt_in_signal(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    write_research_record(
        kb_root / "research" / "R-2026-0001.md",
        ResearchRecord(
            id="R-2026-0001",
            title="Unverified decoder hint",
            body="decoder raw line should only be a snippet",
            tags=["decoder"],
            created="2026-06-16T00:00:00+00:00",
            updated="2026-06-16T00:00:00+00:00",
            expires_at="2026-08-15T00:00:00+00:00",
        ),
    )
    reviewer = MCPHandlers(
        repo_root=tmp_path,
        kb_root=kb_root,
        roles_config=roles_config,
        user="reviewer",
    )
    reader = MCPHandlers(
        repo_root=tmp_path,
        kb_root=kb_root,
        roles_config=roles_config,
        user="reader",
    )

    signals = reviewer.search_research_for_hints("decoder")["research_signals"]

    assert [signal["id"] for signal in signals] == ["R-2026-0001"]
    assert signals[0]["trust_state"] == "research"
    assert signals[0]["warning"] == "unverified_research，不可用于判责"
    assert "snippet" in signals[0]
    assert "body" not in signals[0]
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
