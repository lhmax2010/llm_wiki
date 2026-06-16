"""Physically isolated research storage and promote service."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from governed_api.audit import append_audit_record, preflight_audit_path
from governed_api.roles import ADMIN_PERMISSION, RolesConfig
from governed_api.types import ApiError, AuditRecord
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.id_allocator import IDAllocator
from core.models import AuthorType, Entry, TrustState
from core.storage import FRONTMATTER_MARKER, read_frontmatter, write_entry
from core.validation import ID_PATTERN, validate_entry

LOGGER = logging.getLogger(__name__)

RESEARCH_ID_PATTERN = re.compile(r"^R-(?P<year>\d{4})-(?P<number>\d{4})$")
DEFAULT_TTL_DAYS = 60
CREATE_RESEARCH_PERMISSION = "create_research"
UPDATE_RESEARCH_PERMISSION = "edit_own_research"
PROMOTE_RESEARCH_PERMISSION = "promote_research_to_draft"
RESEARCH_DIR: Literal["research"] = "research"
DRAFTS_DIR: Literal["drafts"] = "drafts"
INDEXES_DIR: Literal["indexes"] = "indexes"


class ResearchRecord(BaseModel):
    """Unverified research material stored outside the formal Entry schema."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    module: str = ""
    body: str
    trust_state: Literal["research"] = "research"
    tags: list[str] = Field(default_factory=list)
    author: str | None = None
    created: str
    updated: str
    expires_at: str | None = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def require_research_id(cls, value: str) -> str:
        if RESEARCH_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("research id must match R-{year}-{NNNN}")
        return value


@dataclass(frozen=True, slots=True)
class ResearchOperationResult:
    ok: bool
    error: ApiError | None
    record: ResearchRecord | None = None
    entry: Entry | None = None
    source_path: Path | None = None
    target_path: Path | None = None
    audit_record: AuditRecord | None = None


@dataclass(frozen=True, slots=True)
class ResearchTTLReport:
    expired_count: int
    active_count: int
    expired_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchIdAllocator:
    """SQLite allocator for physically isolated research ids."""

    db_path: Path

    def allocate(self, *, year: int | None = None) -> str:
        target_year = year or datetime.now().year
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path, timeout=30)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ids(year INTEGER PRIMARY KEY, next INTEGER NOT NULL)"
            )
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next FROM ids WHERE year = ?",
                (target_year,),
            ).fetchone()
            if row is None:
                next_number = 1
                connection.execute(
                    "INSERT INTO ids(year, next) VALUES (?, ?)",
                    (target_year, 2),
                )
            else:
                next_number = int(row[0])
                connection.execute(
                    "UPDATE ids SET next = ? WHERE year = ?",
                    (next_number + 1, target_year),
                )
            connection.commit()
        return f"R-{target_year:04d}-{next_number:04d}"


@dataclass(frozen=True, slots=True)
class ResearchStore:
    kb_root: Path
    repo_root: Path
    roles_config: RolesConfig
    user: str
    author_type: AuthorType = AuthorType.HUMAN
    audit_path: Path | None = None
    research_id_allocator: ResearchIdAllocator | None = None
    entry_id_allocator: IDAllocator | None = None
    ttl_days: int = DEFAULT_TTL_DAYS

    def create_research(
        self,
        *,
        title: str,
        body: str,
        module: str = "",
        tags: list[str] | None = None,
    ) -> ResearchOperationResult:
        permission_error = self._permission_error(CREATE_RESEARCH_PERMISSION)
        if permission_error is not None:
            return _failed(permission_error)
        if not title.strip():
            return _failed(ApiError("E_SCHEMA", "research title is required", "title"))
        if not body.strip():
            return _failed(ApiError("E_SCHEMA", "research body is required", "body"))

        audit_path = self._audit_path()
        try:
            preflight_audit_path(audit_path)
        except OSError as exc:
            return _failed(ApiError("E_SCHEMA", f"audit path is not writable: {exc}", "audit_path"))

        record = ResearchRecord(
            id=self._research_allocator().allocate(),
            title=title,
            module=module,
            body=body,
            tags=tags or [],
            author=self.user,
            created=_now(),
            updated=_now(),
            expires_at=(datetime.now(UTC) + timedelta(days=self.ttl_days)).isoformat(),
        )
        path = _research_path(self.kb_root, record.id)
        try:
            write_research_record(path, record)
        except OSError as exc:
            return _failed(ApiError("E_SCHEMA", f"research write failed: {exc}", "research"))
        audit_record = _build_research_audit_record(
            kb_root=self.kb_root,
            path=path,
            user=self.user,
            role=self._role(),
            operation="create_research",
            research_id=record.id,
            target_dir=RESEARCH_DIR,
        )
        try:
            append_audit_record(audit_path, audit_record)
        except OSError as exc:
            _rollback_path(path)
            return _failed(ApiError("E_SCHEMA", f"audit append failed: {exc}", "audit_path"))
        return ResearchOperationResult(
            ok=True,
            error=None,
            record=record,
            source_path=path,
            audit_record=audit_record,
        )

    def update_research(
        self,
        *,
        research_id: str,
        title: str | None = None,
        body: str | None = None,
        module: str | None = None,
        tags: list[str] | None = None,
    ) -> ResearchOperationResult:
        permission_error = self._permission_error(UPDATE_RESEARCH_PERMISSION)
        if permission_error is not None:
            return _failed(permission_error)
        loaded = _load_research_record(self.kb_root, research_id)
        if loaded is None:
            return _failed(ApiError("E_SCHEMA", f"research not found: {research_id}", "id"))
        record, path = loaded
        updated = record.model_copy(
            update={
                "title": title if title is not None else record.title,
                "body": body if body is not None else record.body,
                "module": module if module is not None else record.module,
                "tags": tags if tags is not None else record.tags,
                "updated": _now(),
            }
        )
        audit_path = self._audit_path()
        try:
            preflight_audit_path(audit_path)
            write_research_record(path, updated)
            audit_record = _build_research_audit_record(
                kb_root=self.kb_root,
                path=path,
                user=self.user,
                role=self._role(),
                operation="update_research",
                research_id=updated.id,
                target_dir=RESEARCH_DIR,
            )
            append_audit_record(audit_path, audit_record)
        except OSError as exc:
            return _failed(ApiError("E_SCHEMA", f"research update failed: {exc}", "research"))
        return ResearchOperationResult(
            ok=True,
            error=None,
            record=updated,
            source_path=path,
            audit_record=audit_record,
        )

    def promote_research_to_draft(
        self,
        *,
        research_id: str,
        draft: dict[str, Any],
        note: str | None = None,
    ) -> ResearchOperationResult:
        permission_error = self._permission_error(PROMOTE_RESEARCH_PERMISSION)
        if permission_error is not None:
            return _failed(permission_error)
        if "id" in draft:
            return _failed(ApiError("E_SCHEMA", "promote draft must not include id", "draft.id"))
        loaded = _load_research_record(self.kb_root, research_id)
        if loaded is None:
            return _failed(ApiError("E_SCHEMA", f"research not found: {research_id}", "id"))
        research_record, research_path = loaded

        try:
            lock_path = _acquire_research_lock(self.kb_root, research_id)
        except FileExistsError:
            return _failed(ApiError("E_DUP", "research promote already in progress", "id"))
        except (OSError, ValueError) as exc:
            return _failed(ApiError("E_SCHEMA", f"research lock cannot be acquired: {exc}", "id"))

        try:
            if _draft_exists_for_research(self.kb_root, research_id):
                return _failed(ApiError("E_DUP", "research has already been promoted", "id"))
            return self._locked_promote(
                research_record=research_record,
                research_path=research_path,
                draft=draft,
                note=note,
            )
        finally:
            _release_research_lock(lock_path)

    def ttl_report(self, *, now: datetime | None = None) -> ResearchTTLReport:
        current = now or datetime.now(UTC)
        records, _ = read_valid_research_from_source(self.kb_root, context="research ttl")
        expired: list[str] = []
        active = 0
        for item in records:
            expires_at = _parse_datetime(item.record.expires_at)
            if expires_at is not None and expires_at <= current:
                expired.append(item.record.id)
            else:
                active += 1
        return ResearchTTLReport(
            expired_count=len(expired),
            active_count=active,
            expired_ids=tuple(sorted(expired)),
        )

    def _locked_promote(
        self,
        *,
        research_record: ResearchRecord,
        research_path: Path,
        draft: dict[str, Any],
        note: str | None,
    ) -> ResearchOperationResult:
        audit_path = self._audit_path()
        try:
            preflight_audit_path(audit_path)
        except OSError as exc:
            return _failed(ApiError("E_SCHEMA", f"audit path is not writable: {exc}", "audit_path"))

        entry_id = self._entry_allocator().allocate()
        now = _now()
        payload = dict(draft)
        payload.setdefault("schema_version", 3)
        payload.setdefault("title", research_record.title)
        payload.setdefault("module", research_record.module)
        payload.setdefault("body", research_record.body)
        payload.setdefault("author", self.user)
        payload.setdefault("created", now)
        payload["updated"] = now
        payload["id"] = entry_id
        payload["trust_state"] = TrustState.DRAFT.value
        payload["author_type"] = AuthorType.HUMAN.value
        source_refs = list(payload.get("source_refs", []))
        source_refs.append({"type": "research", "id": research_record.id})
        payload["source_refs"] = source_refs
        try:
            entry = Entry.model_validate(payload)
        except ValidationError as exc:
            return _failed(
                ApiError(
                    "E_SCHEMA",
                    "promoted draft failed Entry schema validation",
                    "draft",
                    exc.errors(),
                )
            )

        target_path = _target_path(self.kb_root, DRAFTS_DIR, entry.id)
        report = validate_entry(
            entry,
            repo_root=self.repo_root,
            kb_root=self.kb_root,
            entry_path=target_path,
        )
        if not report.ok:
            primary = report.errors[0]
            return _failed(
                ApiError(
                    primary.code.value,
                    "promoted draft failed validation",
                    primary.field,
                    report.errors,
                )
            )
        try:
            write_entry(target_path, report.entry)
        except OSError as exc:
            return _failed(ApiError("E_SCHEMA", f"draft write failed: {exc}", "draft"))

        post_write = validate_entry(
            report.entry,
            repo_root=self.repo_root,
            kb_root=self.kb_root,
            entry_path=target_path,
        )
        if not post_write.ok:
            _rollback_path(target_path)
            primary = post_write.errors[0]
            return _failed(
                ApiError(primary.code.value, "draft failed post-write validation", primary.field)
            )

        audit_record = _build_research_audit_record(
            kb_root=self.kb_root,
            path=target_path,
            user=self.user,
            role=self._role(),
            operation="promote_research_to_draft",
            research_id=research_record.id,
            target_dir=DRAFTS_DIR,
            entry_id=post_write.entry.id,
            note=note,
        )
        try:
            append_audit_record(audit_path, audit_record)
        except OSError as exc:
            _rollback_path(target_path)
            return _failed(ApiError("E_SCHEMA", f"audit append failed: {exc}", "audit_path"))

        return ResearchOperationResult(
            ok=True,
            error=None,
            record=research_record,
            entry=post_write.entry,
            source_path=research_path,
            target_path=target_path,
            audit_record=audit_record,
        )

    def _permission_error(self, permission: str) -> ApiError | None:
        if self.author_type == AuthorType.AGENT:
            return ApiError(
                "E_PERM", "agent cannot create/update/promote research", "auth.author_type"
            )
        try:
            _role, permissions = self.roles_config.permissions_for_user(self.user)
        except KeyError:
            return ApiError("E_PERM", f"unknown user: {self.user}", "auth.user")
        if ADMIN_PERMISSION not in permissions and permission not in permissions:
            return ApiError("E_PERM", f"permission required: {permission}", "auth.permissions")
        return None

    def _role(self) -> str:
        return self.roles_config.permissions_for_user(self.user)[0]

    def _audit_path(self) -> Path:
        return self.audit_path or self.kb_root / INDEXES_DIR / "audit.jsonl"

    def _research_allocator(self) -> ResearchIdAllocator:
        return self.research_id_allocator or ResearchIdAllocator(
            self.kb_root / INDEXES_DIR / "research_ids.sqlite"
        )

    def _entry_allocator(self) -> IDAllocator:
        return self.entry_id_allocator or IDAllocator(self.kb_root / INDEXES_DIR / "ids.sqlite")


@dataclass(frozen=True, slots=True)
class ValidResearchRecord:
    record: ResearchRecord
    path: Path


def read_valid_research_from_source(
    kb_root: Path,
    *,
    context: str,
) -> tuple[list[ValidResearchRecord], int]:
    directory = _source_root(kb_root, RESEARCH_DIR)
    if not directory.exists():
        return [], 0
    records: list[ValidResearchRecord] = []
    skipped = 0
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        item = read_valid_research_record_file(kb_root, path, context=context)
        if item is None:
            skipped += 1
            continue
        records.append(item)
    return records, skipped


def read_valid_research_record_file(
    kb_root: Path,
    path: Path,
    *,
    context: str,
) -> ValidResearchRecord | None:
    source_root = _source_root(kb_root, RESEARCH_DIR)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        LOGGER.warning("%s: skipping unresolvable research path: %s (%s)", context, path, exc)
        return None
    if not resolved.is_file():
        return None
    if not resolved.is_relative_to(source_root):
        LOGGER.warning("%s: skipping research path outside source dir: %s", context, resolved)
        return None
    try:
        record = read_research_record(resolved)
    except (OSError, ValidationError, ValueError) as exc:
        LOGGER.warning("%s: skipping unreadable research file: %s (%s)", context, resolved, exc)
        return None
    if record.id != resolved.stem:
        LOGGER.warning(
            "%s: skipping research filename/id mismatch: filename=%s record.id=%s",
            context,
            resolved.stem,
            record.id,
        )
        return None
    return ValidResearchRecord(record=record, path=resolved)


def read_research_record(path: Path) -> ResearchRecord:
    frontmatter, body = read_frontmatter(path)
    payload = dict(frontmatter)
    payload["body"] = body
    return ResearchRecord.model_validate(payload)


def write_research_record(path: Path, record: ResearchRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = record.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    document = (
        f"{FRONTMATTER_MARKER}\n"
        f"{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)}"
        f"{FRONTMATTER_MARKER}\n"
        f"{record.body.rstrip()}\n"
    )
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            tmp_name = handle.name
            handle.write(document)
        os.replace(tmp_name, path)
    finally:
        if tmp_name is not None and Path(tmp_name).exists():
            Path(tmp_name).unlink()


def _load_research_record(kb_root: Path, research_id: str) -> tuple[ResearchRecord, Path] | None:
    if RESEARCH_ID_PATTERN.fullmatch(research_id) is None:
        return None
    path = _research_path(kb_root, research_id)
    if not path.is_file():
        return None
    item = read_valid_research_record_file(kb_root, path, context="research load")
    if item is None:
        return None
    return item.record, item.path


def _research_path(kb_root: Path, research_id: str) -> Path:
    if RESEARCH_ID_PATTERN.fullmatch(research_id) is None:
        raise ValueError("invalid research id")
    return _target_path(kb_root, RESEARCH_DIR, research_id)


def _target_path(kb_root: Path, source_dir: Literal["research", "drafts"], item_id: str) -> Path:
    if source_dir == RESEARCH_DIR and RESEARCH_ID_PATTERN.fullmatch(item_id) is None:
        raise ValueError("invalid research id")
    if source_dir == DRAFTS_DIR and ID_PATTERN.fullmatch(item_id) is None:
        raise ValueError("invalid entry id")
    root = _source_root(kb_root, source_dir)
    path = (root / f"{item_id}.md").resolve()
    if not path.is_relative_to(root):
        raise ValueError("target path escapes source directory")
    return path


def _source_root(kb_root: Path, source_dir: Literal["research", "drafts", "indexes"]) -> Path:
    root = kb_root.resolve()
    source_path = root / source_dir
    if source_path.exists() and source_path.is_symlink():
        raise ValueError(f"{source_dir} directory must not be a symlink")
    resolved = source_path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{source_dir} directory escapes kb root")
    return resolved


def _draft_exists_for_research(kb_root: Path, research_id: str) -> bool:
    try:
        from index.sqlite_index import read_valid_entries_from_source
    except ImportError:
        return False
    try:
        entries, _ = read_valid_entries_from_source(
            kb_root, DRAFTS_DIR, context="research promote duplicate scan"
        )
    except ValueError:
        return False
    return any(
        any(
            ref.get("type") == "research" and ref.get("id") == research_id
            for ref in entry.source_refs
        )
        for entry in (item.entry for item in entries)
    )


def _acquire_research_lock(kb_root: Path, research_id: str) -> Path:
    if RESEARCH_ID_PATTERN.fullmatch(research_id) is None:
        raise ValueError("invalid research id")
    root = kb_root.resolve()
    lock_dir = _source_root(kb_root, INDEXES_DIR) / "research_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    resolved_lock_dir = lock_dir.resolve()
    if not resolved_lock_dir.is_relative_to(root):
        raise ValueError("research lock directory escapes kb root")
    lock_path = resolved_lock_dir / f"{research_id}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{_now()}\n")
    return lock_path


def _release_research_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        LOGGER.error("research lock cleanup failed: %s (%s)", lock_path, exc)


def _build_research_audit_record(
    *,
    kb_root: Path,
    path: Path,
    user: str,
    role: str,
    operation: str,
    research_id: str,
    target_dir: str,
    entry_id: str | None = None,
    note: str | None = None,
) -> AuditRecord:
    try:
        relative_path = path.resolve().relative_to(kb_root.resolve()).as_posix()
    except ValueError:
        relative_path = path.name
    record: AuditRecord = {
        "timestamp": _now(),
        "user": user,
        "role": role,
        "operation": operation,
        "entry_id": entry_id or research_id,
        "target_dir": target_dir,
        "path": relative_path,
    }
    if note:
        record["note"] = note
    return record


def _rollback_path(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        LOGGER.error(
            "research rollback failed: %s (%s) - orphaned research artifact remains", path, exc
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _failed(error: ApiError) -> ResearchOperationResult:
    return ResearchOperationResult(ok=False, error=error)
