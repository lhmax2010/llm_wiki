"""Staging review lifecycle service.

Phase 5 deliberately keeps the review surface as a small Python service. Web/API
layers can call it later, but the state transition rules stay testable here.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from governed_api.audit import append_audit_record, preflight_audit_path
from governed_api.roles import ADMIN_PERMISSION, RolesConfig
from governed_api.types import ApiError, AuditRecord, ReviewLevel
from pydantic import ValidationError

from core.models import Entry, TrustState
from core.storage import read_entry, write_entry
from core.validation import ID_PATTERN, validate_entry

LOGGER = logging.getLogger(__name__)

BACKLOG_WARNING_THRESHOLD = 50
LIGHT_PERMISSION = "review_light"
HEAVY_PERMISSION = "review_heavy"
PUBLISH_PERMISSION = "publish_entry"
DEPRECATE_PERMISSION = "deprecate_entry"
VALID_QUEUE_LEVELS: set[ReviewLevel] = {"light", "heavy"}
ReviewDecision = Literal["approve", "reject"]


@dataclass(frozen=True, slots=True)
class ReviewQueueItem:
    entry_id: str
    title: str
    module: str
    entry_type: str
    claim_type: str
    support_strength: str
    review_level: ReviewLevel
    updated: str
    path: str


@dataclass(frozen=True, slots=True)
class ReviewQueue:
    items: tuple[ReviewQueueItem, ...]
    backlog_count: int
    backlog_warning: bool
    skipped_files: int


@dataclass(frozen=True, slots=True)
class ReviewOperationResult:
    ok: bool
    error: ApiError | None
    entry: Entry | None = None
    warning: ApiError | None = None
    review_level: ReviewLevel | None = None
    source_path: Path | None = None
    target_path: Path | None = None
    audit_record: AuditRecord | None = None


def list_review_queue(
    *,
    kb_root: Path,
    repo_root: Path,
    audit_path: Path | None = None,
) -> ReviewQueue:
    """Return validated pending staging entries for reviewer triage."""

    levels = _review_levels_from_audit(audit_path or _default_audit_path(kb_root))
    items: list[ReviewQueueItem] = []
    skipped = 0
    try:
        staging_root = _source_root(kb_root, "staging")
    except ValueError as exc:
        LOGGER.warning("review queue: invalid staging root (%s)", exc)
        return ReviewQueue(items=(), backlog_count=0, backlog_warning=False, skipped_files=0)
    if not staging_root.exists():
        return ReviewQueue(items=(), backlog_count=0, backlog_warning=False, skipped_files=0)

    for candidate in sorted(staging_root.glob("*.md")):
        entry_id = candidate.stem
        if not _valid_entry_id(entry_id):
            LOGGER.warning("review queue: skipping invalid staging filename: %s", candidate)
            skipped += 1
            continue
        terminal_path = _terminal_entry_path(kb_root, entry_id)
        if terminal_path is not None:
            LOGGER.warning(
                "review queue: skipping staging residue because terminal entry exists: %s (%s)",
                entry_id,
                terminal_path,
            )
            skipped += 1
            continue
        loaded = _load_entry_for_state(
            kb_root=kb_root,
            repo_root=repo_root,
            source_dir="staging",
            entry_id=entry_id,
            expected_state=TrustState.PENDING,
        )
        if loaded is None:
            skipped += 1
            continue
        entry, resolved = loaded
        level = levels.get(entry.id, "heavy")
        if level not in VALID_QUEUE_LEVELS:
            level = "heavy"
        items.append(_queue_item(entry, level, resolved, kb_root))

    return ReviewQueue(
        items=tuple(items),
        backlog_count=len(items),
        backlog_warning=len(items) > BACKLOG_WARNING_THRESHOLD,
        skipped_files=skipped,
    )


def approve_staging_entry(
    *,
    kb_root: Path,
    repo_root: Path,
    roles_config: RolesConfig,
    reviewer: str,
    entry_id: str,
    note: str | None = None,
    audit_path: Path | None = None,
) -> ReviewOperationResult:
    return _review_transition(
        kb_root=kb_root,
        repo_root=repo_root,
        roles_config=roles_config,
        reviewer=reviewer,
        entry_id=entry_id,
        decision="approve",
        target_dir="entries",
        target_state=TrustState.PUBLISHED,
        action_permission=PUBLISH_PERMISSION,
        note=note,
        audit_path=audit_path,
    )


def reject_staging_entry(
    *,
    kb_root: Path,
    repo_root: Path,
    roles_config: RolesConfig,
    reviewer: str,
    entry_id: str,
    note: str | None = None,
    audit_path: Path | None = None,
) -> ReviewOperationResult:
    return _review_transition(
        kb_root=kb_root,
        repo_root=repo_root,
        roles_config=roles_config,
        reviewer=reviewer,
        entry_id=entry_id,
        decision="reject",
        target_dir="deprecated",
        target_state=TrustState.DEPRECATED,
        action_permission=DEPRECATE_PERMISSION,
        note=note,
        audit_path=audit_path,
    )


def _review_transition(
    *,
    kb_root: Path,
    repo_root: Path,
    roles_config: RolesConfig,
    reviewer: str,
    entry_id: str,
    decision: ReviewDecision,
    target_dir: Literal["entries", "deprecated"],
    target_state: TrustState,
    action_permission: str,
    note: str | None,
    audit_path: Path | None,
) -> ReviewOperationResult:
    if not _valid_entry_id(entry_id):
        return _failed("E_SCHEMA", "entry_id must match KB-{year}-{NNNN}", "entry_id")

    resolved_audit_path = audit_path or _default_audit_path(kb_root)
    review_level = _review_levels_from_audit(resolved_audit_path).get(entry_id, "heavy")
    if review_level not in VALID_QUEUE_LEVELS:
        review_level = "heavy"
    permission_error = _review_permission_error(
        roles_config,
        reviewer,
        review_level=review_level,
        action_permission=action_permission,
    )
    if permission_error is not None:
        return ReviewOperationResult(ok=False, error=permission_error, review_level=review_level)

    try:
        preflight_audit_path(resolved_audit_path)
    except OSError as exc:
        return _failed("E_SCHEMA", f"audit path is not writable: {exc}", "audit_path")

    try:
        terminal_path = _terminal_entry_path(kb_root, entry_id)
    except ValueError as exc:
        return _failed("E_SCHEMA", f"invalid terminal directory: {exc}", "kb_root")
    if terminal_path is not None:
        return _failed("E_DUP", f"terminal entry already exists: {terminal_path}", "entry_id")

    try:
        lock_path = _acquire_review_lock(kb_root, entry_id)
    except FileExistsError:
        return _failed("E_DUP", "review already in progress for entry", "entry_id")
    except OSError as exc:
        return _failed("E_SCHEMA", f"review lock cannot be acquired: {exc}", "entry_id")
    except ValueError as exc:
        return _failed("E_SCHEMA", f"invalid review lock path: {exc}", "kb_root")

    try:
        return _locked_review_transition(
            kb_root=kb_root,
            repo_root=repo_root,
            roles_config=roles_config,
            reviewer=reviewer,
            entry_id=entry_id,
            decision=decision,
            target_dir=target_dir,
            target_state=target_state,
            note=note,
            review_level=review_level,
            resolved_audit_path=resolved_audit_path,
        )
    finally:
        _release_review_lock(lock_path)


def _locked_review_transition(
    *,
    kb_root: Path,
    repo_root: Path,
    roles_config: RolesConfig,
    reviewer: str,
    entry_id: str,
    decision: ReviewDecision,
    target_dir: Literal["entries", "deprecated"],
    target_state: TrustState,
    note: str | None,
    review_level: ReviewLevel,
    resolved_audit_path: Path,
) -> ReviewOperationResult:
    try:
        terminal_path = _terminal_entry_path(kb_root, entry_id)
    except ValueError as exc:
        return _failed("E_SCHEMA", f"invalid terminal directory: {exc}", "kb_root")
    if terminal_path is not None:
        return _failed("E_DUP", f"terminal entry already exists: {terminal_path}", "entry_id")

    check_evidence_exists = decision == "approve"
    loaded = _load_entry_for_state(
        kb_root=kb_root,
        repo_root=repo_root,
        source_dir="staging",
        entry_id=entry_id,
        expected_state=TrustState.PENDING,
        check_evidence_exists=check_evidence_exists,
    )
    if loaded is None:
        return _failed("E_SCHEMA", "staging entry not found or invalid", "entry_id")
    source_entry, source_path = loaded

    target_path = _target_path(kb_root, target_dir, entry_id)
    reviewed = source_entry.model_copy(
        update={
            "trust_state": target_state,
            "reviewer": reviewer,
            "updated": datetime.now(UTC).isoformat(),
        }
    )
    target_report = validate_entry(
        reviewed,
        repo_root=repo_root,
        kb_root=kb_root,
        entry_path=target_path,
        check_evidence_exists=check_evidence_exists,
    )
    if not target_report.ok:
        return _failed(
            target_report.errors[0].code.value,
            "entry validation failed before review persist",
            target_report.errors[0].field,
        )
    reviewed = target_report.entry

    try:
        write_entry(target_path, reviewed)
    except OSError as exc:
        return _failed("E_SCHEMA", f"review target write failed: {exc}", "target_path")

    post_write = _load_entry_for_state(
        kb_root=kb_root,
        repo_root=repo_root,
        source_dir=target_dir,
        entry_id=entry_id,
        expected_state=target_state,
        check_evidence_exists=check_evidence_exists,
    )
    if post_write is None:
        _rollback_target(target_path)
        return _failed("E_SCHEMA", "review target failed post-write validation", "target_path")
    reviewed = post_write[0]

    record = _build_review_audit_record(
        kb_root=kb_root,
        path=target_path,
        reviewer=reviewer,
        role=roles_config.permissions_for_user(reviewer)[0],
        decision=decision,
        entry_id=entry_id,
        target_dir=target_dir,
        review_level=review_level,
        note=note,
    )
    try:
        append_audit_record(resolved_audit_path, record)
    except OSError as exc:
        _rollback_target(target_path)
        return _failed("E_SCHEMA", f"audit append failed: {exc}", "audit_path")

    try:
        source_path.unlink()
    except OSError as exc:
        LOGGER.error(
            "review source cleanup failed: %s (%s) - duplicate staging residue remains",
            source_path,
            exc,
        )
        warning = ApiError(
            "E_SCHEMA",
            f"review source cleanup failed: {exc}",
            "source_path",
        )
        return ReviewOperationResult(
            ok=True,
            error=None,
            warning=warning,
            entry=reviewed,
            review_level=review_level,
            source_path=source_path,
            target_path=target_path,
            audit_record=record,
        )

    return ReviewOperationResult(
        ok=True,
        error=None,
        entry=reviewed,
        review_level=review_level,
        source_path=source_path,
        target_path=target_path,
        audit_record=record,
    )


def _load_entry_for_state(
    *,
    kb_root: Path,
    repo_root: Path,
    source_dir: Literal["staging", "entries", "deprecated"],
    entry_id: str,
    expected_state: TrustState,
    check_evidence_exists: bool = True,
) -> tuple[Entry, Path] | None:
    try:
        path = _existing_entry_path(kb_root, source_dir, entry_id)
    except ValueError as exc:
        LOGGER.warning("review service: invalid entry path for %s (%s)", entry_id, exc)
        return None
    try:
        entry = read_entry(path)
    except (OSError, ValidationError, ValueError) as exc:
        LOGGER.warning("review service: skipping unreadable entry file: %s (%s)", path, exc)
        return None
    if entry.id != entry_id:
        LOGGER.warning(
            "review service: filename/id mismatch: filename=%s entry.id=%s",
            entry_id,
            entry.id,
        )
        return None
    if entry.trust_state != expected_state:
        LOGGER.warning(
            "review service: entry has unexpected trust_state: %s (%s)",
            path,
            entry.trust_state,
        )
        return None
    report = validate_entry(
        entry,
        repo_root=repo_root,
        kb_root=kb_root,
        entry_path=path,
        check_evidence_exists=check_evidence_exists,
    )
    if not report.ok:
        issues = "; ".join(
            f"{issue.code.value}:{issue.field}:{issue.message}" for issue in report.errors
        )
        LOGGER.warning("review service: skipping invalid entry file: %s (%s)", path, issues)
        return None
    return report.entry, path


def _existing_entry_path(
    kb_root: Path,
    source_dir: Literal["staging", "entries", "deprecated"],
    entry_id: str,
) -> Path:
    if not _valid_entry_id(entry_id):
        raise ValueError("invalid entry id")
    root = _source_root(kb_root, source_dir)
    candidate = root / f"{entry_id}.md"
    if not candidate.exists():
        raise ValueError("entry file does not exist")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"entry path cannot resolve: {exc}") from exc
    if not resolved.is_file():
        raise ValueError("entry path is not a regular file")
    if not resolved.is_relative_to(root):
        raise ValueError("entry path escapes source directory")
    return resolved


def _target_path(
    kb_root: Path,
    target_dir: Literal["entries", "deprecated"],
    entry_id: str,
) -> Path:
    if not _valid_entry_id(entry_id):
        raise ValueError("invalid entry id")
    root = _source_root(kb_root, target_dir)
    path = (root / f"{entry_id}.md").resolve()
    if not path.is_relative_to(root):
        raise ValueError("target path escapes source directory")
    return path


def _terminal_entry_path(kb_root: Path, entry_id: str) -> Path | None:
    for terminal_dir in ("entries", "deprecated"):
        path = _target_path(kb_root, terminal_dir, entry_id)
        if path.exists():
            return path
    return None


def _source_root(
    kb_root: Path,
    source_dir: Literal["staging", "entries", "deprecated", "indexes"],
) -> Path:
    root = kb_root.resolve()
    source_path = root / source_dir
    if source_path.exists() and source_path.is_symlink():
        raise ValueError(f"{source_dir} directory must not be a symlink")
    resolved = source_path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{source_dir} directory escapes kb root")
    return resolved


def _valid_entry_id(entry_id: str) -> bool:
    return ID_PATTERN.fullmatch(entry_id) is not None


def _queue_item(
    entry: Entry, review_level: ReviewLevel, path: Path, kb_root: Path
) -> ReviewQueueItem:
    return ReviewQueueItem(
        entry_id=entry.id,
        title=entry.title,
        module=entry.module,
        entry_type=entry.entry_type.value,
        claim_type=entry.credibility.claim_type.value,
        support_strength=entry.credibility.support_strength.value,
        review_level=review_level,
        updated=entry.updated,
        path=path.relative_to(kb_root.resolve()).as_posix(),
    )


def _review_permission_error(
    roles_config: RolesConfig,
    user: str,
    *,
    review_level: ReviewLevel,
    action_permission: str,
) -> ApiError | None:
    try:
        _role, permissions = roles_config.permissions_for_user(user)
    except KeyError:
        return ApiError("E_PERM", f"unknown reviewer: {user}", "reviewer")
    required_review_permission = LIGHT_PERMISSION if review_level == "light" else HEAVY_PERMISSION
    missing = [
        permission
        for permission in (required_review_permission, action_permission)
        if ADMIN_PERMISSION not in permissions and permission not in permissions
    ]
    if missing:
        return ApiError(
            "E_PERM",
            f"permission required: {', '.join(missing)}",
            "auth.permissions",
        )
    return None


def _build_review_audit_record(
    *,
    kb_root: Path,
    path: Path,
    reviewer: str,
    role: str,
    decision: ReviewDecision,
    entry_id: str,
    target_dir: Literal["entries", "deprecated"],
    review_level: ReviewLevel,
    note: str | None,
) -> AuditRecord:
    try:
        relative_path = path.resolve().relative_to(kb_root.resolve()).as_posix()
    except ValueError:
        relative_path = path.name
    record: AuditRecord = {
        "timestamp": datetime.now(UTC).isoformat(),
        "user": reviewer,
        "role": role,
        "operation": f"review_{decision}",
        "entry_id": entry_id,
        "target_dir": target_dir,
        "path": relative_path,
        "decision": decision,
        "reviewer": reviewer,
        "review_level": review_level,
    }
    if note:
        record["note"] = note
    return record


def _review_levels_from_audit(audit_path: Path) -> dict[str, ReviewLevel]:
    levels: dict[str, ReviewLevel] = {}
    if not audit_path.is_file():
        return levels
    try:
        lines = audit_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        LOGGER.warning("review service: cannot read audit log for review levels: %s", exc)
        return levels
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            LOGGER.warning(
                "review service: skipping invalid audit line %s (%s)",
                line_number,
                exc,
            )
            continue
        if not isinstance(record, dict):
            continue
        entry_id = record.get("entry_id")
        level = record.get("review_level")
        if (
            isinstance(entry_id, str)
            and _valid_entry_id(entry_id)
            and level in VALID_QUEUE_LEVELS
            and record.get("target_dir") == "staging"
        ):
            levels[entry_id] = level
    return levels


def _rollback_target(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        LOGGER.error(
            "review target rollback failed: %s (%s) - orphaned review target remains",
            path,
            exc,
        )


def _acquire_review_lock(kb_root: Path, entry_id: str) -> Path:
    root = kb_root.resolve()
    lock_dir = _source_root(kb_root, "indexes") / "review_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    resolved_lock_dir = lock_dir.resolve()
    if not resolved_lock_dir.is_relative_to(root):
        raise ValueError("review lock directory escapes kb root")
    lock_path = resolved_lock_dir / f"{entry_id}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(lock_path, flags)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{datetime.now(UTC).isoformat()}\n")
    return lock_path


def _release_review_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        LOGGER.error("review lock cleanup failed: %s (%s)", lock_path, exc)


def _default_audit_path(kb_root: Path) -> Path:
    return kb_root / "indexes" / "audit.jsonl"


def _failed(code: str, message: str, field: str | None) -> ReviewOperationResult:
    return ReviewOperationResult(ok=False, error=ApiError(code, message, field))
