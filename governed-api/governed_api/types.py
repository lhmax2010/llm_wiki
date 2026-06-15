"""Shared types for the Governed API middleware pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Required, TypedDict

from core.errors import ValidationIssue
from core.id_allocator import IDAllocator
from core.models import Entry

ReviewLevel = Literal["auto", "light", "heavy"]
TargetDir = Literal["research", "drafts", "staging", "entries"]


@dataclass(frozen=True, slots=True)
class ApiError:
    code: str
    message: str
    field: str | None = None
    details: object | None = None


class AuthInfo(TypedDict, total=False):
    user: Required[str]
    role: str
    permissions: list[str]


class AuditRecord(TypedDict):
    timestamp: str
    user: str
    role: str
    operation: str
    entry_id: str
    target_dir: str
    path: str


class MiddlewareContext(TypedDict, total=False):
    auth: Required[AuthInfo]
    operation: Required[str]
    payload: Required[dict[str, Any]]
    target_dir: TargetDir
    validation_errors: list[ValidationIssue]
    validation_warnings: list[ValidationIssue]
    review_level: ReviewLevel
    repo_root: Path
    kb_root: Path
    entry_path: Path
    entry: Entry
    previous_payload: dict[str, Any]
    previous_entry: Entry
    changed_fields: list[str]
    change_scopes: list[str]
    id_allocator: IDAllocator
    audit_path: Path
    persisted_path: Path
    audit_record: AuditRecord
    allocated_id: str
    id_was_missing: bool


class MiddlewareResult(TypedDict):
    ok: bool
    context: MiddlewareContext
    error: ApiError | None


Middleware = Callable[[MiddlewareContext], MiddlewareResult]


def ok(context: MiddlewareContext) -> MiddlewareResult:
    return {"ok": True, "context": context, "error": None}


def fail(context: MiddlewareContext, error: ApiError) -> MiddlewareResult:
    return {"ok": False, "context": context, "error": error}
