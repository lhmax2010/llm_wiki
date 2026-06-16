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
from typing import Any, cast

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
from pydantic import ValidationError

from core.id_allocator import IDAllocator
from core.models import Entry
from core.storage import read_entry
from index import IndexUnavailable, SearchService
from mcp.kb_server.types import ProposeResult, SearchResult, SearchScope

LOGGER = logging.getLogger(__name__)
KB_ID_RE = re.compile(r"^KB-\d{4}-\d{4}$")

PUBLISHED_DIR = "entries"
PENDING_DIR = "staging"
SUPPORT_RANK = {"weak": 0, "moderate": 1, "strong": 2}


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
        scope = scope or {}
        matched_results: list[tuple[Entry, SearchResult]] = []
        for entry in self._scan_entries(include_pending=include_pending):
            result = _search_result_for(entry, query=query, scope=scope)
            if result is not None:
                matched_results.append((entry, result))
        sorted_results = _sort_results(matched_results, sort)
        return sorted_results[max(offset, 0) : max(offset, 0) + max(limit, 0)]

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
            entries.extend(_read_entries_from_dir(self.kb_root / dirname))
        return entries

    def _find_entry(self, entry_id: str, *, dirs: Iterable[str]) -> Entry | None:
        for dirname in dirs:
            path = _entry_path(self.kb_root, dirname, entry_id)
            if path.is_file():
                try:
                    return read_entry(path)
                except (OSError, ValidationError, ValueError) as exc:
                    LOGGER.warning("skipping unreadable entry file: %s (%s)", path, exc)
                    raise ToolError("E_SCHEMA", f"entry is unreadable: {entry_id}", "id") from exc
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


def _read_entries_from_dir(directory: Path) -> list[Entry]:
    if not directory.exists():
        return []
    entries: list[Entry] = []
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        try:
            entries.append(read_entry(path))
        except (OSError, ValidationError, ValueError) as exc:
            LOGGER.warning("skipping unreadable entry file: %s (%s)", path, exc)
    return entries


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


def _search_result_for(entry: Entry, *, query: str, scope: SearchScope) -> SearchResult | None:
    matched_section_raw = _scope_matched_section(entry, scope)
    if matched_section_raw is _NO_MATCH:
        return None
    matched_section = cast(str | None, matched_section_raw)
    if not _matches_query(entry, query):
        return None
    snippet = _snippet(entry, query)
    score = _score(entry, query)
    stale = bool(entry.code_binding.stale) if entry.code_binding is not None else False
    return SearchResult(
        {
            "id": entry.id,
            "title": entry.title,
            "entry_type": entry.entry_type.value,
            "module": entry.module,
            "snippet": snippet,
            "matched_section": matched_section,
            "credibility": entry.credibility.model_dump(mode="json"),
            "trust_state": entry.trust_state.value,
            "stale": stale,
            "score": score,
        }
    )


_NO_MATCH = object()


def _scope_matched_section(entry: Entry, scope: SearchScope) -> str | None | object:
    if scope.get("module") not in (None, entry.module):
        return _NO_MATCH
    if scope.get("entry_type") not in (None, entry.entry_type.value):
        return _NO_MATCH
    if scope.get("error_code") is not None and scope["error_code"] not in entry.error_codes:
        return _NO_MATCH
    if scope.get("claim_type") not in (None, entry.credibility.claim_type.value):
        return _NO_MATCH
    if scope.get("status") not in (None, entry.trust_state.value):
        return _NO_MATCH
    if scope.get("exclude_stale") and entry.code_binding is not None and entry.code_binding.stale:
        return _NO_MATCH
    min_support = scope.get("min_support")
    if min_support is None:
        return None
    return _support_match(entry, min_support)


def _support_match(entry: Entry, min_support: str) -> str | None | object:
    minimum = SUPPORT_RANK.get(min_support)
    if minimum is None:
        return _NO_MATCH
    if SUPPORT_RANK[entry.credibility.support_strength.value] >= minimum:
        return None
    for section, credibility in entry.section_credibility.items():
        support = credibility.support_strength
        if support is not None and SUPPORT_RANK[support.value] >= minimum:
            return section
    return _NO_MATCH


def _matches_query(entry: Entry, query: str) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return True
    return normalized in _entry_search_text(entry)


def _entry_search_text(entry: Entry) -> str:
    parts = [
        entry.id,
        entry.title,
        entry.module,
        entry.body,
        *entry.tags,
        *entry.aliases,
        *entry.symptom_keywords,
        *entry.error_codes,
        *entry.log_signatures,
    ]
    return "\n".join(parts).lower()


def _snippet(entry: Entry, query: str) -> str:
    normalized = query.strip().lower()
    lines = [entry.title, *entry.body.splitlines()]
    if normalized:
        for line in lines:
            if normalized in line.lower():
                return line.strip()[:240]
    return entry.title[:240]


def _score(entry: Entry, query: str) -> int:
    normalized = query.strip().lower()
    if not normalized:
        return 0
    score = 0
    if normalized in entry.title.lower():
        score += 10
    if normalized in entry.module.lower():
        score += 4
    if normalized in entry.body.lower():
        score += 2
    if any(normalized in value.lower() for value in entry.tags + entry.aliases):
        score += 3
    if any(normalized in value.lower() for value in entry.error_codes):
        score += 5
    return score


def _sort_results(results: list[tuple[Entry, SearchResult]], sort: str) -> list[SearchResult]:
    if sort == "updated_desc":
        return [
            result
            for _, result in sorted(
                results, key=lambda item: (item[0].updated, item[0].id), reverse=True
            )
        ]
    if sort == "title":
        return [result for _, result in sorted(results, key=lambda item: item[1]["title"])]
    return [
        result
        for _, result in sorted(
            results,
            key=lambda item: (item[1].get("score", 0), item[0].updated, item[0].id),
            reverse=True,
        )
    ]


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
