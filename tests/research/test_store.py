from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governed_api.roles import RolesConfig

from core.id_allocator import IDAllocator
from core.models import AuthorType
from core.storage import read_entry
from research.store import ResearchIdAllocator, ResearchRecord, ResearchStore, write_research_record
from tests.governed_api.helpers import entry_payload


def test_create_research_uses_independent_id_and_audit(tmp_path: Path) -> None:
    store = _store(tmp_path)

    result = store.create_research(title="Unverified decoder note", body="raw decoder hint")

    assert result.ok
    assert result.record is not None
    assert result.record.id == "R-2026-0001"
    assert (tmp_path / "kb" / "research" / "R-2026-0001.md").exists()
    assert not (tmp_path / "kb" / "entries" / "R-2026-0001.md").exists()
    assert (tmp_path / "kb" / "indexes" / "audit.jsonl").read_text(encoding="utf-8")


def test_agent_cannot_create_update_or_promote_research(tmp_path: Path) -> None:
    human = _store(tmp_path)
    created = human.create_research(title="Agent blocked note", body="raw").record
    assert created is not None
    agent = _store(tmp_path, author_type=AuthorType.AGENT)

    create_result = agent.create_research(title="bad", body="bad")
    update_result = agent.update_research(research_id=created.id, body="bad")
    promote_result = agent.promote_research_to_draft(
        research_id=created.id,
        draft=_draft_payload(),
    )

    assert create_result.error is not None
    assert create_result.error.code == "E_PERM"
    assert update_result.error is not None
    assert update_result.error.code == "E_PERM"
    assert promote_result.error is not None
    assert promote_result.error.code == "E_PERM"


def test_promote_research_copies_to_new_draft_id_and_keeps_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_research(title="Decoder research", body="raw decoder hint").record
    assert created is not None

    result = store.promote_research_to_draft(
        research_id=created.id,
        draft=_draft_payload(title="Formal decoder draft"),
        note="ready for review",
    )

    assert result.ok
    assert result.entry is not None
    assert result.entry.id == "KB-2026-0001"
    assert result.entry.trust_state.value == "draft"
    assert result.entry.source_refs[-1] == {"type": "research", "id": "R-2026-0001"}
    assert result.source_path == tmp_path / "kb" / "research" / "R-2026-0001.md"
    assert result.source_path.exists()
    assert result.target_path == tmp_path / "kb" / "drafts" / "KB-2026-0001.md"
    assert result.target_path.exists()
    assert read_entry(result.target_path).trust_state.value == "draft"


def test_promote_research_rejects_self_declared_draft_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_research(title="Decoder research", body="raw decoder hint").record
    assert created is not None
    draft = _draft_payload()
    draft["id"] = "KB-2026-9999"

    result = store.promote_research_to_draft(research_id=created.id, draft=draft)

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_SCHEMA"
    assert not (tmp_path / "kb" / "drafts" / "KB-2026-9999.md").exists()


def test_promote_research_is_idempotent_by_source_ref(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_research(title="Decoder research", body="raw decoder hint").record
    assert created is not None

    first = store.promote_research_to_draft(research_id=created.id, draft=_draft_payload())
    second = store.promote_research_to_draft(research_id=created.id, draft=_draft_payload())

    assert first.ok
    assert not second.ok
    assert second.error is not None
    assert second.error.code == "E_DUP"


def test_ttl_report_marks_expired_without_deleting_research(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    expired = ResearchRecord(
        id="R-2026-0001",
        title="expired",
        body="old raw",
        created="2026-01-01T00:00:00+00:00",
        updated="2026-01-01T00:00:00+00:00",
        expires_at="2026-01-02T00:00:00+00:00",
    )
    active = ResearchRecord(
        id="R-2026-0002",
        title="active",
        body="new raw",
        created="2026-01-01T00:00:00+00:00",
        updated="2026-01-01T00:00:00+00:00",
        expires_at="2026-02-01T00:00:00+00:00",
    )
    write_research_record(kb_root / "research" / "R-2026-0001.md", expired)
    write_research_record(kb_root / "research" / "R-2026-0002.md", active)
    store = _store(tmp_path)

    report = store.ttl_report(now=datetime(2026, 1, 3, tzinfo=UTC))

    assert report.expired_count == 1
    assert report.active_count == 1
    assert report.expired_ids == ("R-2026-0001",)
    assert (kb_root / "research" / "R-2026-0001.md").exists()


def _store(tmp_path: Path, *, author_type: AuthorType = AuthorType.HUMAN) -> ResearchStore:
    kb_root = tmp_path / "kb"
    return ResearchStore(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=RolesConfig(
            roles={
                "contributor": [
                    "read_published",
                    "create_research",
                    "edit_own_research",
                    "promote_research_to_draft",
                ],
            },
            users={"alice": "contributor"},
        ),
        user="alice",
        author_type=author_type,
        research_id_allocator=ResearchIdAllocator(kb_root / "indexes" / "research_ids.sqlite"),
        entry_id_allocator=IDAllocator(kb_root / "indexes" / "ids.sqlite"),
        ttl_days=30,
    )


def _draft_payload(*, title: str = "Formal decoder draft") -> dict[str, Any]:
    payload = entry_payload(entry_id=None, trust_state="draft", title=title)
    payload.pop("id", None)
    payload["trust_state"] = "draft"
    return payload
