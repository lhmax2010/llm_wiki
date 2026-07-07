from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest
from governed_api.roles import RolesConfig
from governed_api.types import ApiError, AuditRecord, ReviewLevel

from core.models import AuthorType, Entry
from core.storage import read_entry, write_entry
from review.service import (
    BACKLOG_WARNING_THRESHOLD,
    approve_staging_entry,
    get_review_detail,
    list_review_queue,
    reject_staging_entry,
)
from tests.governed_api.helpers import body_for, entry_payload


@pytest.fixture
def review_roles() -> RolesConfig:
    return RolesConfig(
        roles={
            "contributor": ["read_published", "propose_entry"],
            "light_reviewer": ["review_light", "publish_entry", "deprecate_entry"],
            "reviewer": [
                "read_published",
                "propose_entry",
                "review_light",
                "review_heavy",
                "publish_entry",
                "deprecate_entry",
            ],
            "admin": ["*"],
        },
        users={
            "alice": "contributor",
            "light": "light_reviewer",
            "reviewer": "reviewer",
            "admin": "admin",
        },
    )


def test_review_queue_lists_valid_pending_entries_with_system_review_level(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    staging_entry = _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(kb_root, staging_entry.id, target_dir="staging", review_level="light")

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.backlog_count == 1
    assert not queue.backlog_warning
    assert queue.items[0].entry_id == "KB-2026-0001"
    assert queue.items[0].review_level == "light"
    assert queue.items[0].path == "staging/KB-2026-0001.md"


def test_review_queue_defaults_unknown_review_level_to_heavy(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.items[0].review_level == "heavy"


def test_review_queue_includes_entry_with_stale_code_evidence(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(
        kb_root,
        "staging",
        "KB-2026-0001",
        trust_state="pending",
        claim_type="static_inference",
        evidence=[{"type": "code", "filepath": "src/missing.c"}],
    )

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.backlog_count == 1
    assert queue.items[0].entry_id == "KB-2026-0001"


def test_review_queue_skips_invalid_state_and_published_duplicate(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="published")
    _write_entry(kb_root, "staging", "KB-2026-0002", trust_state="pending")
    _write_entry(kb_root, "entries", "KB-2026-0002", trust_state="published")
    caplog.set_level(logging.WARNING, logger="review.service")

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.items == ()
    assert queue.skipped_files == 2
    assert "unexpected trust_state" in caplog.text
    assert "terminal entry exists" in caplog.text


def test_review_queue_includes_update_proposal_with_published_target(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.backlog_count == 1
    assert queue.items[0].entry_id == "KB-2026-0001"
    assert queue.items[0].review_level == "heavy"


def test_review_detail_returns_pending_proposal_without_published_diff(
    tmp_path: Path,
) -> None:
    kb_root = tmp_path / "kb"
    staging_entry = _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(kb_root, staging_entry.id, target_dir="staging", review_level="light")

    detail = get_review_detail(kb_root=kb_root, repo_root=tmp_path, entry_id=staging_entry.id)

    assert not isinstance(detail, ApiError)
    assert detail.entry_id == staging_entry.id
    assert detail.review_level == "light"
    assert detail.operation == "create"
    assert detail.proposal.id == staging_entry.id
    assert detail.proposal.trust_state == "pending"
    assert detail.proposal_path == kb_root / "staging" / "KB-2026-0001.md"
    assert detail.published is None
    assert detail.changed_fields == ()
    assert detail.diff_available is False


def test_review_detail_update_diff_is_current_published_vs_staging(
    tmp_path: Path,
) -> None:
    kb_root = tmp_path / "kb"
    published = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    proposal_body = entry_payload(entry_id=None)["body"].replace("content.", "proposal body.")
    proposal = _write_entry(
        kb_root,
        "staging",
        "KB-2026-0001",
        trust_state="pending",
        body=proposal_body,
    )
    proposal = proposal.model_copy(
        update={
            "updated": "2026-07-07T02:00:00Z",
            "author": "alice",
            "author_type": AuthorType.HUMAN,
        }
    )
    write_entry(kb_root / "staging" / "KB-2026-0001.md", proposal)
    current_published = published.model_copy(
        update={
            "body": "## symptom\ncurrent v2 body",
            "updated": "2026-07-07T01:00:00Z",
            "author": "bob",
            "author_type": AuthorType.AGENT,
        }
    )
    write_entry(kb_root / "entries" / "KB-2026-0001.md", current_published)
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    detail = get_review_detail(kb_root=kb_root, repo_root=tmp_path, entry_id="KB-2026-0001")

    assert not isinstance(detail, ApiError)
    assert detail.operation == "propose_update"
    assert detail.published is not None
    assert detail.published.body == "## symptom\ncurrent v2 body"
    assert detail.proposal.body == proposal.body
    assert detail.diff_available is True
    assert detail.changed_fields == ("body",)
    assert "trust_state" not in detail.changed_fields
    assert "updated" not in detail.changed_fields
    assert "author" not in detail.changed_fields
    assert "author_type" not in detail.changed_fields


def test_review_detail_refuses_terminal_residue_and_invalid_id(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _write_entry(kb_root, "deprecated", "KB-2026-0001", trust_state="deprecated")

    terminal = get_review_detail(kb_root=kb_root, repo_root=tmp_path, entry_id="KB-2026-0001")
    invalid = get_review_detail(kb_root=kb_root, repo_root=tmp_path, entry_id="../research/x")

    assert isinstance(terminal, ApiError)
    assert terminal.code == "E_DUP"
    assert terminal.field == "entry_id"
    assert isinstance(invalid, ApiError)
    assert invalid.code == "E_SCHEMA"
    assert invalid.field == "entry_id"


def test_review_queue_skips_when_any_terminal_state_exists(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _write_entry(kb_root, "deprecated", "KB-2026-0001", trust_state="deprecated")
    caplog.set_level(logging.WARNING, logger="review.service")

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.items == ()
    assert queue.skipped_files == 1
    assert "terminal entry exists" in caplog.text


def test_review_queue_reports_backlog_warning(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    for number in range(1, BACKLOG_WARNING_THRESHOLD + 2):
        _write_entry(kb_root, "staging", f"KB-2026-{number:04d}", trust_state="pending")

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)

    assert queue.backlog_count == BACKLOG_WARNING_THRESHOLD + 1
    assert queue.backlog_warning


def test_approve_publishes_with_same_id_updates_review_metadata_and_audits(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    staging_entry = _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(kb_root, staging_entry.id, target_dir="staging", review_level="heavy")

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id=staging_entry.id,
        note="content verified",
    )

    assert result.ok, result.error
    assert result.review_level == "heavy"
    assert result.target_path == kb_root / "entries" / "KB-2026-0001.md"
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    published = read_entry(kb_root / "entries" / "KB-2026-0001.md")
    assert published.id == staging_entry.id
    assert published.trust_state == "published"
    assert published.reviewer == "reviewer"
    assert published.created == staging_entry.created
    assert published.updated != staging_entry.updated

    audit = _last_audit(kb_root)
    assert audit["operation"] == "review_approve"
    assert audit["entry_id"] == staging_entry.id
    assert audit["target_dir"] == "entries"
    assert audit["path"] == "entries/KB-2026-0001.md"
    assert audit["review_level"] == "heavy"
    assert audit["decision"] == "approve"
    assert audit["reviewer"] == "reviewer"
    assert audit["note"] == "content verified"


def test_approve_republishes_update_proposal_and_audits(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    original = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    updated_body = entry_payload(entry_id=None)["body"].replace("content.", "republished.")
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending", body=updated_body)
    _append_audit(
        kb_root,
        original.id,
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id=original.id,
        note="republish accepted",
    )

    assert result.ok, result.error
    assert result.target_path == kb_root / "entries" / "KB-2026-0001.md"
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    republished = read_entry(kb_root / "entries" / "KB-2026-0001.md")
    assert republished.id == original.id
    assert republished.body == updated_body
    assert republished.trust_state == "published"
    assert republished.reviewer == "reviewer"
    audit = _last_audit(kb_root)
    assert audit["operation"] == "review_republish"
    assert audit["decision"] == "approve"
    assert audit["target_dir"] == "entries"
    assert audit["review_level"] == "heavy"
    assert audit["note"] == "republish accepted"


def test_approve_net_new_still_rejects_existing_published_target(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    existing = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_entry",
    )

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_DUP"
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").updated == existing.updated
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()


def test_republish_still_rejects_deprecated_terminal_conflict(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    existing = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    _write_entry(kb_root, "deprecated", "KB-2026-0001", trust_state="deprecated")
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_DUP"
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").updated == existing.updated
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()


def test_reject_moves_to_deprecated_and_keeps_reject_audit(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    entry = _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    _append_audit(kb_root, entry.id, target_dir="staging", review_level="light")

    result = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="light",
        entry_id=entry.id,
        note="duplicate report",
    )

    assert result.ok, result.error
    assert result.review_level == "light"
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    rejected = read_entry(kb_root / "deprecated" / "KB-2026-0001.md")
    assert rejected.id == entry.id
    assert rejected.trust_state == "deprecated"
    assert rejected.reviewer == "light"
    audit = _last_audit(kb_root)
    assert audit["operation"] == "review_reject"
    assert audit["decision"] == "reject"
    assert audit["target_dir"] == "deprecated"
    assert audit["review_level"] == "light"


def test_permissions_use_roles_config_for_light_and_heavy(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    light_entry = _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    heavy_entry = _write_entry(kb_root, "staging", "KB-2026-0002", trust_state="pending")
    _append_audit(kb_root, light_entry.id, target_dir="staging", review_level="light")
    _append_audit(kb_root, heavy_entry.id, target_dir="staging", review_level="heavy")

    light_ok = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="light",
        entry_id=light_entry.id,
    )
    heavy_denied = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="light",
        entry_id=heavy_entry.id,
    )
    contributor_denied = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="alice",
        entry_id=heavy_entry.id,
    )

    assert light_ok.ok
    assert not heavy_denied.ok
    assert heavy_denied.error is not None
    assert heavy_denied.error.code == "E_PERM"
    assert "review_heavy" in heavy_denied.error.message
    assert not contributor_denied.ok
    assert contributor_denied.error is not None
    assert "review_heavy" in contributor_denied.error.message
    assert "deprecate_entry" in contributor_denied.error.message


def test_review_rejects_bad_id_and_missing_or_invalid_staging_entry(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="published")

    bad_id = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="../research/KB-2026-0001",
    )
    invalid_state = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not bad_id.ok
    assert bad_id.error is not None
    assert bad_id.error.field == "entry_id"
    assert not invalid_state.ok
    assert invalid_state.error is not None
    assert invalid_state.error.field == "entry_id"
    assert not (kb_root / "entries" / "KB-2026-0001.md").exists()


def test_review_refuses_transition_when_any_terminal_state_exists(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    existing = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    _write_entry(kb_root, "staging", "KB-2026-0002", trust_state="pending")
    _write_entry(kb_root, "deprecated", "KB-2026-0002", trust_state="deprecated")

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )
    deprecated_result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0002",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_DUP"
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").updated == existing.updated
    assert not deprecated_result.ok
    assert deprecated_result.error is not None
    assert deprecated_result.error.code == "E_DUP"
    assert (kb_root / "staging" / "KB-2026-0002.md").exists()


def test_review_lock_blocks_concurrent_transition(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    lock_dir = kb_root / "indexes" / "review_locks"
    lock_dir.mkdir(parents=True)
    (lock_dir / "KB-2026-0001.lock").write_text("already running\n", encoding="utf-8")

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "E_DUP"
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()
    assert not (kb_root / "entries" / "KB-2026-0001.md").exists()


def test_state_directory_symlink_is_rejected(tmp_path: Path, review_roles: RolesConfig) -> None:
    kb_root = tmp_path / "kb"
    outside = tmp_path / "outside-staging"
    kb_root.mkdir()
    outside.mkdir()
    try:
        os.symlink(outside, kb_root / "staging", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink not available on this host: {exc}")

    queue = list_review_queue(kb_root=kb_root, repo_root=tmp_path)
    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert queue.items == ()
    assert not result.ok
    assert result.error is not None
    assert result.error.field == "entry_id"


def test_terminal_directory_symlink_is_rejected(tmp_path: Path, review_roles: RolesConfig) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")
    outside_entries = tmp_path / "outside-entries"
    outside_deprecated = tmp_path / "outside-deprecated"
    outside_entries.mkdir()
    outside_deprecated.mkdir()
    try:
        os.symlink(outside_entries, kb_root / "entries", target_is_directory=True)
        os.symlink(outside_deprecated, kb_root / "deprecated", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink not available on this host: {exc}")

    approve_result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )
    reject_result = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not approve_result.ok
    assert approve_result.error is not None
    assert approve_result.error.field == "kb_root"
    assert not reject_result.ok
    assert reject_result.error is not None
    assert reject_result.error.field == "kb_root"


def test_reject_can_dispose_entry_with_stale_code_evidence(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    entry = _write_entry(
        kb_root,
        "staging",
        "KB-2026-0001",
        trust_state="pending",
        claim_type="static_inference",
        evidence=[{"type": "code", "filepath": "src/missing.c"}],
    )

    approved = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id=entry.id,
    )
    rejected = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id=entry.id,
    )

    assert not approved.ok
    assert approved.error is not None
    assert approved.error.code == "E_SCHEMA"
    assert rejected.ok, rejected.error
    assert read_entry(kb_root / "deprecated" / "KB-2026-0001.md").trust_state == "deprecated"


def test_reject_can_dispose_entry_with_invalid_body(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    entry = _write_entry(
        kb_root,
        "staging",
        "KB-2026-0001",
        trust_state="pending",
        body="## incomplete\ninvalid skeleton",
    )

    approved = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id=entry.id,
    )
    rejected = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id=entry.id,
    )

    assert not approved.ok
    assert approved.error is not None
    assert approved.error.code == "E_SCHEMA"
    assert rejected.ok, rejected.error
    assert read_entry(kb_root / "deprecated" / "KB-2026-0001.md").trust_state == "deprecated"


def test_reject_update_proposal_keeps_published_and_discards_staging(
    tmp_path: Path, review_roles: RolesConfig
) -> None:
    kb_root = tmp_path / "kb"
    code_binding: dict[str, object] = {
        "repo_id": "local",
        "git_sha": "abc123",
        "paths": ["logs/baseline.txt"],
    }
    existing = _write_entry(
        kb_root,
        "entries",
        "KB-2026-0001",
        trust_state="published",
        entry_type="log_baseline",
        code_binding=code_binding,
    )
    updated_body = body_for("log_baseline").replace("content.", "updated proposal.")
    _write_entry(
        kb_root,
        "staging",
        "KB-2026-0001",
        trust_state="pending",
        entry_type="log_baseline",
        body=updated_body,
        code_binding=code_binding,
    )
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="light",
        operation="propose_update",
    )

    result = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="light",
        entry_id="KB-2026-0001",
        note="keep current published baseline",
    )

    assert result.ok, result.error
    assert result.entry is not None
    assert result.entry.trust_state == "published"
    assert result.target_path == kb_root / "entries" / "KB-2026-0001.md"
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").body == existing.body
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    assert not (kb_root / "deprecated" / "KB-2026-0001.md").exists()
    audit = _last_audit(kb_root)
    assert audit["operation"] == "review_reject_update"
    assert audit["decision"] == "reject"
    assert audit["target_dir"] == "staging"
    assert audit["path"] == "staging/KB-2026-0001.md"
    assert audit["note"] == "keep current published baseline"


def test_reject_update_audit_failure_keeps_staging_and_published(
    tmp_path: Path, review_roles: RolesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_root = tmp_path / "kb"
    existing = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    updated_body = entry_payload(entry_id=None)["body"].replace("content.", "rejected update.")
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending", body=updated_body)
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    def fail_append(*args: object, **kwargs: object) -> None:
        raise OSError("audit blocked")

    monkeypatch.setattr("review.service.append_audit_record", fail_append)

    result = reject_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.field == "audit_path"
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").body == existing.body
    assert not (kb_root / "deprecated" / "KB-2026-0001.md").exists()


def test_audit_append_failure_rolls_back_target_and_keeps_staging(
    tmp_path: Path, review_roles: RolesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")

    def fail_append(*args: object, **kwargs: object) -> None:
        raise OSError("audit blocked")

    monkeypatch.setattr("review.service.append_audit_record", fail_append)

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.field == "audit_path"
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()
    assert not (kb_root / "entries" / "KB-2026-0001.md").exists()


def test_republish_audit_failure_restores_existing_published_entry(
    tmp_path: Path, review_roles: RolesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_root = tmp_path / "kb"
    existing = _write_entry(kb_root, "entries", "KB-2026-0001", trust_state="published")
    updated_body = entry_payload(entry_id=None)["body"].replace("content.", "republished.")
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending", body=updated_body)
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    def fail_append(*args: object, **kwargs: object) -> None:
        raise OSError("audit blocked")

    monkeypatch.setattr("review.service.append_audit_record", fail_append)

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.field == "audit_path"
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()
    restored = read_entry(kb_root / "entries" / "KB-2026-0001.md")
    assert restored.body == existing.body
    assert restored.updated == existing.updated


def test_source_cleanup_failure_is_reported_after_audited_publish(
    tmp_path: Path,
    review_roles: RolesConfig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    kb_root = tmp_path / "kb"
    _write_entry(kb_root, "staging", "KB-2026-0001", trust_state="pending")

    original_unlink = Path.unlink

    def fail_unlink(self: Path) -> None:
        if self.name == "KB-2026-0001.md":
            raise OSError("source locked")
        original_unlink(self)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    caplog.set_level(logging.ERROR, logger="review.service")

    result = approve_staging_entry(
        kb_root=kb_root,
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001",
    )

    assert result.ok
    assert result.error is None
    assert result.warning is not None
    assert result.warning.field == "staging_residue"
    assert (kb_root / "entries" / "KB-2026-0001.md").exists()
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()
    assert "source cleanup failed" in caplog.text
    assert _last_audit(kb_root)["operation"] == "review_approve"


def test_entry_id_validation_uses_fullmatch(tmp_path: Path, review_roles: RolesConfig) -> None:
    result = approve_staging_entry(
        kb_root=tmp_path / "kb",
        repo_root=tmp_path,
        roles_config=review_roles,
        reviewer="reviewer",
        entry_id="KB-2026-0001\n",
    )

    assert not result.ok
    assert result.error is not None
    assert result.error.field == "entry_id"


def _write_entry(
    kb_root: Path,
    directory: str,
    entry_id: str,
    *,
    trust_state: str,
    entry_type: str = "defect_case",
    claim_type: str = "observation",
    evidence: list[dict[str, object]] | None = None,
    body: str | None = None,
    code_binding: dict[str, object] | None = None,
) -> Entry:
    payload = entry_payload(
        entry_id=entry_id,
        trust_state=trust_state,
        claim_type=claim_type,
        evidence=evidence,
        body=body if body is not None else body_for(entry_type),
    )
    payload["entry_type"] = entry_type
    if code_binding is not None:
        payload["code_binding"] = code_binding
    entry = Entry.model_validate(payload)
    write_entry(kb_root / directory / f"{entry_id}.md", entry)
    return entry


def _append_audit(
    kb_root: Path,
    entry_id: str,
    *,
    target_dir: str,
    review_level: ReviewLevel,
    operation: str = "create",
) -> None:
    audit_path = kb_root / "indexes" / "audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    record: AuditRecord = {
        "timestamp": "2026-06-16T00:00:00+00:00",
        "user": "alice",
        "role": "contributor",
        "operation": operation,
        "entry_id": entry_id,
        "target_dir": target_dir,
        "path": f"{target_dir}/{entry_id}.md",
        "review_level": review_level,
    }
    with audit_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _last_audit(kb_root: Path) -> dict[str, object]:
    lines = (kb_root / "indexes" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    value = json.loads(lines[-1])
    assert isinstance(value, dict)
    return value
