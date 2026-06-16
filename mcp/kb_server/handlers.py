"""Phase 3 MCP tool handlers.

The handlers are deliberately transport-agnostic. The MCP stdio wrapper calls this
module, and tests can exercise the governance boundary without a running subprocess.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_api import (
    ApiError,
    MiddlewareContext,
    RolesConfig,
    audit_append,
    auth_context,
    classify_write_route,
    evidence_validate,
    persist,
    review_route,
    run_pipeline,
    schema_validate,
)
from governed_api.types import Middleware

from core.id_allocator import IDAllocator
from core.models import Entry
from index import IndexUnavailable, SearchService
from index.sqlite_index import read_valid_entries_from_source, read_valid_entry_file
from mcp.kb_server.types import ProposeResult, SearchResult, SearchScope

LOGGER = logging.getLogger(__name__)
KB_ID_RE = re.compile(r"^KB-\d{4}-\d{4}$")

PUBLISHED_DIR = "entries"
PENDING_DIR = "staging"


class ToolError(Exception):
    """Raised when an MCP tool cannot complete."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "field": self.field, "message": self.message}


@dataclass(frozen=True, slots=True)
class MCPHandlers:
    """Agent-facing tool handlers backed by content-core and Governed API."""

    repo_root: Path
    kb_root: Path
    roles_config: RolesConfig
    user: str
    id_allocator: IDAllocator | None = None
    audit_path: Path | None = None
    pipeline_steps: tuple[Middleware, ...] | None = None
    search_service: SearchService | None = None

    def search_kb(
        self,
        query: str,
        scope: SearchScope | None = None,
        include_pending: bool = False,
        expand_synonyms: bool = True,
        limit: int = 20,
        offset: int = 0,
        sort: str = "score",
    ) -> list[SearchResult]:
        self._require("read_published")
        service = self.search_service or SearchService(self.kb_root)
        try:
            return service.search_agent(
                query,
                scope=scope,
                include_pending=include_pending,
                expand_synonyms=expand_synonyms,
                limit=limit,
                offset=offset,
                sort=sort,
            )
        except IndexUnavailable as exc:
            LOGGER.warning("search index unavailable, falling back to directory scan: %s", exc)
        return service.search_agent_direct(
            query,
            scope=scope,
            include_pending=include_pending,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def get_entry(self, id: str, include_pending: bool = False) -> dict[str, Any]:
        self._require("read_published")
        entry = self._find_entry(id, dirs=_read_dirs(include_pending=include_pending))
        if entry is None:
            raise ToolError("E_SCHEMA", f"entry not found: {id}", "id")
        return entry.model_dump(mode="json")

    def list_categories(self) -> dict[str, list[str]]:
        self._require("read_published")
        entries = self._scan_entries(include_pending=False)
        return {
            "modules": sorted({entry.module for entry in entries}),
            "entry_types": sorted({entry.entry_type.value for entry in entries}),
            "tags": sorted({tag for entry in entries for tag in entry.tags}),
            "error_codes": sorted({code for entry in entries for code in entry.error_codes}),
        }

    def browse(self, module: str, entry_type: str | None = None) -> dict[str, Any]:
        self._require("read_published")
        entries = [
            entry
            for entry in self._scan_entries(include_pending=False)
            if entry.module == module
            and (entry_type is None or entry.entry_type.value == entry_type)
        ]
        return {
            "module": module,
            "entry_type": entry_type,
            "entries": [
                _entry_summary(entry) for entry in sorted(entries, key=lambda item: item.id)
            ],
        }

    def propose_entry(
        self,
        draft: dict[str, Any],
        credibility: dict[str, Any],
        request_id: str,
    ) -> ProposeResult:
        payload = dict(draft)
        payload["credibility"] = credibility
        context = self._base_context(
            operation="propose_entry",
            payload=payload,
            request_id=request_id,
        )
        result = run_pipeline(context, self._pipeline())
        return _propose_result(result["context"], result["error"], include_proposed_id=True)

    def propose_update(
        self,
        id: str,
        patch: dict[str, Any],
        reason: str,
        credibility: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ProposeResult:
        try:
            _validate_entry_id(id)
        except ToolError as exc:
            return _failed_propose_result(exc)
        previous_entry = self._find_entry(id, dirs=_read_dirs(include_pending=True))
        if previous_entry is None:
            return _failed_propose_result(ToolError("E_SCHEMA", f"entry not found: {id}", "id"))
        payload = _merge_update_payload(id, patch, previous_entry)
        if credibility is not None:
            payload["credibility"] = credibility
        context = self._base_context(
            operation="propose_update",
            payload=payload,
            request_id=request_id,
        )
        context["change_scopes"] = list(_as_str_list(patch.get("change_scopes")))
        context["changed_fields"] = list(_as_str_list(patch.get("changed_fields")))
        if previous_entry is not None:
            context["previous_entry"] = previous_entry
        context["update_reason"] = reason  # type: ignore[typeddict-unknown-key]
        result = run_pipeline(context, self._pipeline())
        return _propose_result(result["context"], result["error"], include_proposed_id=False)

    def search_research_for_hints(self, query: str) -> dict[str, list[dict[str, Any]]]:
        del query
        self._require("search_research_for_hints")
        return {"research_signals": []}

    def _base_context(
        self,
        *,
        operation: str,
        payload: dict[str, Any],
        request_id: str | None,
    ) -> MiddlewareContext:
        context: MiddlewareContext = {
            "auth": {"user": self.user},
            "operation": operation,
            "payload": payload,
            "repo_root": self.repo_root,
            "kb_root": self.kb_root,
            "id_allocator": self.id_allocator
            or IDAllocator(self.kb_root / "indexes" / "ids.sqlite"),
        }
        if self.audit_path is not None:
            context["audit_path"] = self.audit_path
        if request_id is not None:
            context["request_id"] = request_id  # type: ignore[typeddict-unknown-key]
        return context

    def _pipeline(self) -> tuple[Middleware, ...]:
        if self.pipeline_steps is not None:
            return self.pipeline_steps
        return (
            auth_context(self.roles_config),
            schema_validate(),
            evidence_validate(),
            classify_write_route(),
            review_route(),
            persist(),
            audit_append(),
        )

    def _scan_entries(self, *, include_pending: bool) -> list[Entry]:
        dirs = [PUBLISHED_DIR]
        if include_pending:
            dirs.append(PENDING_DIR)
        entries: list[Entry] = []
        for dirname in dirs:
            try:
                indexed, _ = read_valid_entries_from_source(
                    self.kb_root, dirname, context=f"MCP {dirname} scan"
                )
            except ValueError as exc:
                LOGGER.warning("skipping invalid MCP scan directory: %s (%s)", dirname, exc)
                continue
            entries.extend(item.entry for item in indexed)
        return entries

    def _find_entry(self, entry_id: str, *, dirs: Iterable[str]) -> Entry | None:
        for dirname in dirs:
            path = _entry_path(self.kb_root, dirname, entry_id)
            if path.is_file():
                try:
                    item = read_valid_entry_file(
                        self.kb_root, dirname, path, context=f"MCP {dirname} entry read"
                    )
                except ValueError as exc:
                    raise ToolError("E_SCHEMA", f"invalid entry source: {dirname}", "dir") from exc
                if item is None:
                    raise ToolError("E_SCHEMA", f"entry is unreadable or invalid: {entry_id}", "id")
                return item.entry
        return None

    def _require(self, permission: str) -> None:
        try:
            role, permissions = self.roles_config.permissions_for_user(self.user)
        except KeyError as exc:
            raise ToolError("E_PERM", f"unknown user: {self.user}", "auth.user") from exc
        if "*" not in permissions and permission not in permissions:
            raise ToolError("E_PERM", f"permission required: {permission}", "auth.permissions")
        if permission == "read_published":
            return
        # Touch role to make it obvious this check is user-mapping based, not caller-declared.
        if not role:
            raise ToolError("E_PERM", f"unknown role for user: {self.user}", "auth.role")


def _read_dirs(*, include_pending: bool) -> tuple[str, ...]:
    return (PUBLISHED_DIR, PENDING_DIR) if include_pending else (PUBLISHED_DIR,)


def _validate_entry_id(entry_id: str) -> str:
    if not KB_ID_RE.fullmatch(entry_id):
        raise ToolError("E_SCHEMA", "id must match KB-{year}-{NNNN}", "id")
    return entry_id


def _entry_path(kb_root: Path, dirname: str, entry_id: str) -> Path:
    _validate_entry_id(entry_id)
    if dirname not in _read_dirs(include_pending=True):
        raise ToolError("E_SCHEMA", f"directory is not MCP-readable: {dirname}", "dir")
    base = (kb_root / dirname).resolve()
    path = (base / f"{entry_id}.md").resolve()
    if not path.is_relative_to(base):
        raise ToolError("E_SCHEMA", "entry path escaped MCP-readable directory", "id")
    return path


def _entry_summary(entry: Entry) -> dict[str, Any]:
    stale = bool(entry.code_binding.stale) if entry.code_binding is not None else False
    return {
        "id": entry.id,
        "title": entry.title,
        "entry_type": entry.entry_type.value,
        "module": entry.module,
        "trust_state": entry.trust_state.value,
        "claim_type": entry.credibility.claim_type.value,
        "support_strength": entry.credibility.support_strength.value,
        "stale": stale,
    }


def _merge_update_payload(
    entry_id: str,
    patch: dict[str, Any],
    previous_entry: Entry | None,
) -> dict[str, Any]:
    patch_without_meta = {
        key: value for key, value in patch.items() if key not in {"changed_fields", "change_scopes"}
    }
    if previous_entry is None:
        payload = dict(patch_without_meta)
        payload["id"] = entry_id
        return payload
    payload = previous_entry.model_dump(mode="json")
    payload.update(patch_without_meta)
    payload["id"] = entry_id
    return payload


def _propose_result(
    context: MiddlewareContext,
    error: ApiError | None,
    *,
    include_proposed_id: bool,
) -> ProposeResult:
    response: ProposeResult = {
        "validation_errors": [
            _issue_to_dict(issue) for issue in context.get("validation_errors", [])
        ],
        "validation_warnings": [
            _issue_to_dict(issue) for issue in context.get("validation_warnings", [])
        ],
        "missing_fields": [],
        "open_questions": [],
        "possible_duplicates": [],
    }
    if error is not None:
        response["validation_errors"].append(_api_error_to_issue(error))
        return response

    entry = context.get("entry")
    if entry is not None:
        response["id"] = entry.id
    if include_proposed_id:
        proposed_id = context.get("allocated_id") or (entry.id if entry is not None else None)
        if proposed_id is not None:
            response["proposed_id"] = proposed_id
    target_dir = context.get("target_dir")
    response["status"] = "auto_published" if target_dir == PUBLISHED_DIR else "pending"
    if "review_level" in context:
        response["review_level"] = context["review_level"]
    return response


def _api_error_to_issue(error: ApiError) -> dict[str, Any]:
    return {"code": error.code, "field": error.field or "", "message": error.message}


def _failed_propose_result(error: ToolError) -> ProposeResult:
    return {
        "validation_errors": [
            {"code": error.code, "field": error.field or "", "message": error.message}
        ],
        "validation_warnings": [],
        "missing_fields": [],
        "open_questions": [],
        "possible_duplicates": [],
    }


def _issue_to_dict(issue: object) -> dict[str, Any]:
    code = getattr(issue, "code", "")
    return {
        "code": getattr(code, "value", str(code)),
        "field": getattr(issue, "field", ""),
        "message": getattr(issue, "message", ""),
    }


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []
