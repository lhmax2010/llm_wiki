from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from governed_api.roles import RolesConfig

from core.id_allocator import IDAllocator
from core.models import AuthorType, TrustState
from core.storage import read_entry, write_entry
from research.store import (
    ResearchIdAllocator,
    ResearchRecord,
    ResearchStore,
    read_research_record,
    write_research_record,
)
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


def test_research_write_requires_system_author_type(tmp_path: Path) -> None:
    store = _store(tmp_path, author_type=None)

    result = store.create_research(title="missing author type", body="raw")

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_PERM"
    assert result.error.field == "auth.author_type"


def test_edit_own_research_enforces_record_owner(tmp_path: Path) -> None:
    roles = _roles_config(users={"alice": "contributor", "bob": "contributor"})
    alice = _store(tmp_path, roles_config=roles, user="alice")
    created = alice.create_research(title="Alice note", body="old").record
    assert created is not None
    bob = _store(tmp_path, roles_config=roles, user="bob")

    denied = bob.update_research(research_id=created.id, body="bob write")

    assert denied.error is not None
    assert denied.error.code == "E_PERM"
    assert read_research_record(tmp_path / "kb" / "research" / f"{created.id}.md").body == "old"
    allowed = alice.update_research(research_id=created.id, body="alice write")

    assert allowed.ok
    assert read_research_record(tmp_path / "kb" / "research" / f"{created.id}.md").body == (
        "alice write"
    )


def test_update_research_rolls_back_when_audit_append_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    created = store.create_research(title="Audit rollback", body="old").record
    assert created is not None

    def fail_append(*_args: object, **_kwargs: object) -> None:
        raise OSError("audit disk full")

    monkeypatch.setattr("research.store.append_audit_record", fail_append)

    result = store.update_research(research_id=created.id, body="new")

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_SCHEMA"
    assert read_research_record(tmp_path / "kb" / "research" / f"{created.id}.md").body == "old"


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


@pytest.mark.parametrize(
    ("target_dir", "target_state"),
    [
        ("staging", TrustState.PENDING),
        ("entries", TrustState.PUBLISHED),
    ],
)
def test_promote_research_is_idempotent_after_draft_leaves_drafts(
    tmp_path: Path,
    target_dir: str,
    target_state: TrustState,
) -> None:
    store = _store(tmp_path)
    created = store.create_research(title="Decoder research", body="raw decoder hint").record
    assert created is not None
    first = store.promote_research_to_draft(research_id=created.id, draft=_draft_payload())
    assert first.ok
    assert first.entry is not None
    assert first.target_path is not None
    moved = first.entry.model_copy(update={"trust_state": target_state})
    first.target_path.unlink()
    write_entry(tmp_path / "kb" / target_dir / f"{moved.id}.md", moved)

    second = store.promote_research_to_draft(research_id=created.id, draft=_draft_payload())

    assert not second.ok
    assert second.error is not None
    assert second.error.code == "E_DUP"


def test_promote_research_fails_closed_when_duplicate_scan_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    created = store.create_research(title="Decoder research", body="raw decoder hint").record
    assert created is not None

    def fail_scan(*_args: object, **_kwargs: object) -> tuple[object, int]:
        raise ValueError("invalid source directory")

    monkeypatch.setattr("research.store._read_valid_entries_from_source", fail_scan)

    result = store.promote_research_to_draft(research_id=created.id, draft=_draft_payload())

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_DUP"
    assert not list((tmp_path / "kb" / "drafts").glob("*.md"))


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


def test_research_id_allocator_validates_year_and_exhaustion(tmp_path: Path) -> None:
    allocator = ResearchIdAllocator(tmp_path / "research_ids.sqlite")

    assert allocator.allocate(year=2026) == "R-2026-0001"
    with pytest.raises(ValueError, match="four-digit"):
        allocator.allocate(year=10000)

    with sqlite3.connect(tmp_path / "research_ids.sqlite") as connection:
        connection.execute("UPDATE ids SET next = ? WHERE year = ?", (10000, 2026))
        connection.commit()

    with pytest.raises(ValueError, match="exhausted"):
        allocator.allocate(year=2026)


def _store(
    tmp_path: Path,
    *,
    author_type: AuthorType | None = AuthorType.HUMAN,
    roles_config: RolesConfig | None = None,
    user: str = "alice",
) -> ResearchStore:
    kb_root = tmp_path / "kb"
    return ResearchStore(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=roles_config or _roles_config(users={"alice": "contributor"}),
        user=user,
        author_type=author_type,
        research_id_allocator=ResearchIdAllocator(kb_root / "indexes" / "research_ids.sqlite"),
        entry_id_allocator=IDAllocator(kb_root / "indexes" / "ids.sqlite"),
        ttl_days=30,
    )


def _roles_config(*, users: dict[str, str]) -> RolesConfig:
    return RolesConfig(
        roles={
            "contributor": [
                "read_published",
                "create_research",
                "edit_own_research",
                "promote_research_to_draft",
            ],
        },
        users=users,
    )


def _draft_payload(*, title: str = "Formal decoder draft") -> dict[str, Any]:
    payload = entry_payload(entry_id=None, trust_state="draft", title=title)
    payload.pop("id", None)
    payload["trust_state"] = "draft"
    return payload
