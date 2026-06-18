"""Service layer for the human Web API surface."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from governed_api import (
    ApiError,
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
from governed_api.roles import ADMIN_PERMISSION
from governed_api.types import Middleware, MiddlewareContext, MiddlewareResult, fail, ok
from pydantic import BaseModel, ConfigDict, Field

from core.id_allocator import IDAllocator
from core.models import CodeBinding, Credibility, Entry, RelatedEdge, SectionCredibility
from index import IndexUnavailable, SearchService
from index.sqlite_index import read_valid_entries_from_source, read_valid_entry_file
from index.types import SearchResult, SearchScope
from review.service import (
    ReviewOperationResult,
    ReviewQueue,
    approve_staging_entry,
    list_review_queue,
    reject_staging_entry,
)

LOGGER = logging.getLogger(__name__)

KB_ID_RE = re.compile(r"^KB-\d{4}-\d{4}$")
PUBLISHED_DIR: Literal["entries"] = "entries"
PENDING_DIR: Literal["staging"] = "staging"
EntryTypeParam = Literal["defect_case", "triage_rule", "code_flow", "log_baseline"]
ClaimTypeParam = Literal[
    "fact",
    "observation",
    "static_inference",
    "historical_pattern",
    "llm_hypothesis",
    "spec",
]
SupportParam = Literal["weak", "moderate", "strong"]
SortParam = Literal["score", "updated_desc", "title"]
WEB_WRITE_SCOPE = "web_edit"
PATH_LIKE_MESSAGE_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:[^/\s]+/)+|(?:^|\s)(?:entries|staging|deprecated|indexes)[\\/])"
)
REVIEW_STORAGE_FIELDS = frozenset({"audit_path", "target_path", "kb_root", "staging_residue"})
REVIEW_PUBLIC_MESSAGES = {
    "audit_path": "review audit operation failed",
    "target_path": "review target operation failed",
    "kb_root": "invalid review storage",
    "staging_residue": "review source cleanup failed",
    "entry_id": "review entry is not available",
}


class WebInputModel(BaseModel):
    """Strict HTTP input model: unlisted fields are caller self-claims."""

    model_config = ConfigDict(extra="forbid")


class WebEntryCreateRequest(WebInputModel):
    entry_type: EntryTypeParam
    title: str = Field(min_length=1, max_length=240)
    module: str = Field(min_length=1, max_length=120)
    credibility: Credibility
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    symptom_keywords: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    log_signatures: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    versions_affected: list[str] = Field(default_factory=list)
    hardware: list[str] = Field(default_factory=list)
    severity: str | None = None
    section_credibility: dict[str, SectionCredibility] = Field(default_factory=dict)
    code_binding: CodeBinding | None = None
    related: list[RelatedEdge] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    trigger: str | None = None
    inferred_fields: list[str] = Field(default_factory=list)


class WebEntryPatchRequest(WebInputModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    module: str | None = Field(default=None, min_length=1, max_length=120)
    credibility: Credibility | None = None
    body: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    symptom_keywords: list[str] | None = None
    error_codes: list[str] | None = None
    log_signatures: list[str] | None = None
    aliases: list[str] | None = None
    versions_affected: list[str] | None = None
    hardware: list[str] | None = None
    severity: str | None = None
    section_credibility: dict[str, SectionCredibility] | None = None
    code_binding: CodeBinding | None = None
    related: list[RelatedEdge] | None = None
    source_refs: list[dict[str, Any]] | None = None
    trigger: str | None = None
    inferred_fields: list[str] | None = None
    reason: str | None = Field(default=None, max_length=500)


class WebReviewDecisionRequest(WebInputModel):
    note: str | None = Field(default=None, max_length=500)


@dataclass(frozen=True, slots=True)
class WebApiError(Exception):
    code: str
    message: str
    field: str | None = None
    status_code: int = 400


@dataclass(frozen=True, slots=True)
class WebReadService:
    """Human read facade backed by P4 safe search and entry readers."""

    kb_root: Path
    search_service: SearchService | None = None

    def search_entries(
        self,
        query: str,
        *,
        scope: SearchScope | None = None,
        expand_synonyms: bool = True,
        limit: int = 20,
        offset: int = 0,
        sort: SortParam = "score",
    ) -> list[SearchResult]:
        service = self.search_service or SearchService(self.kb_root)
        try:
            return service.search_human(
                query,
                scope=scope,
                expand_synonyms=expand_synonyms,
                limit=limit,
                offset=offset,
                sort=sort,
            )
        except IndexUnavailable as exc:
            LOGGER.warning("human search index unavailable, using entries-only fallback: %s", exc)
        return service.search_human_direct(
            query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        path = _published_entry_path(self.kb_root, entry_id)
        if not path.is_file():
            raise WebApiError("E_SCHEMA", f"entry not found: {entry_id}", "id", 404)
        try:
            item = read_valid_entry_file(
                self.kb_root,
                PUBLISHED_DIR,
                path,
                context="web api get_entry",
            )
        except ValueError as exc:
            LOGGER.warning("web api get_entry invalid entry source for %s: %s", entry_id, exc)
            raise WebApiError("E_SCHEMA", "invalid entry source", "id") from exc
        if item is None:
            raise WebApiError("E_SCHEMA", f"entry is unreadable or invalid: {entry_id}", "id", 404)
        return item.entry.model_dump(mode="json")

    def list_categories(self) -> dict[str, list[str]]:
        entries = self._published_entries()
        return {
            "modules": sorted({entry.module for entry in entries}),
            "entry_types": sorted({entry.entry_type.value for entry in entries}),
            "tags": sorted({tag for entry in entries for tag in entry.tags}),
            "error_codes": sorted({code for entry in entries for code in entry.error_codes}),
        }

    def browse(
        self,
        *,
        module: str,
        entry_type: EntryTypeParam | None = None,
    ) -> dict[str, Any]:
        entries = [
            entry
            for entry in self._published_entries()
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

    def graph(self) -> dict[str, Any]:
        entries = sorted(self._published_entries(), key=lambda item: item.id)
        published_ids = {entry.id for entry in entries}
        visual_edges: dict[tuple[str, str], dict[str, Any]] = {}

        for entry in entries:
            for related in entry.related:
                target_id = related.target
                if target_id is None or target_id == entry.id or target_id not in published_ids:
                    continue
                ordered_pair = sorted((entry.id, target_id))
                pair = (ordered_pair[0], ordered_pair[1])
                edge = visual_edges.setdefault(
                    pair,
                    {
                        "source": entry.id,
                        "target": target_id,
                        "types": set(),
                        "origins": set(),
                        "notes": [],
                        "_directions": set(),
                    },
                )
                edge["types"].add(related.type.value if related.type is not None else "related")
                edge["origins"].add(related.origin.value if related.origin is not None else "human")
                if related.note:
                    edge["notes"].append(related.note)
                edge["_directions"].add((entry.id, target_id))

        edges = []
        for pair, edge in sorted(visual_edges.items()):
            directions = edge.pop("_directions")
            bidirectional = len(directions) > 1
            if bidirectional:
                edge["source"], edge["target"] = pair
            edge["bidirectional"] = bidirectional
            edge["types"] = sorted(edge["types"])
            edge["origins"] = sorted(edge["origins"])
            edges.append(edge)

        return {
            "nodes": [_graph_node(entry) for entry in entries],
            "edges": edges,
        }

    def _published_entries(self) -> list[Entry]:
        try:
            indexed, _ = read_valid_entries_from_source(
                self.kb_root,
                PUBLISHED_DIR,
                context="web api published scan",
            )
        except ValueError as exc:
            LOGGER.warning("web api published scan invalid source: %s", exc)
            raise WebApiError("E_SCHEMA", "invalid published source", "kb_root") from exc
        return [item.entry for item in indexed]


@dataclass(frozen=True, slots=True)
class WebWriteService:
    """Human Web write facade backed by the Phase 2 Governed API pipeline."""

    repo_root: Path
    kb_root: Path
    roles_config: RolesConfig
    id_allocator: IDAllocator | None = None
    audit_path: Path | None = None
    pipeline_steps: tuple[Middleware, ...] | None = None

    def propose_entry_from_web(
        self,
        request: WebEntryCreateRequest,
        *,
        user: str,
    ) -> dict[str, Any]:
        now = _utc_now()
        payload = request.model_dump(mode="json", exclude_none=True)
        payload.update(
            {
                "schema_version": 3,
                "trust_state": "pending",
                "author_type": "human",
                "author": user,
                "created": now,
                "updated": now,
            }
        )
        context = self._base_context(user=user, operation="propose_entry", payload=payload)
        result = run_pipeline(context, self._pipeline())
        return _write_result(result, include_proposed_id=True)

    def propose_update_from_web(
        self,
        entry_id: str,
        request: WebEntryPatchRequest,
        *,
        user: str,
    ) -> dict[str, Any]:
        _validate_kb_id(entry_id)
        if self._pending_entry_exists(entry_id):
            return _failed_write_result(
                ApiError("E_DUP", f"pending proposal already exists: {entry_id}", "id")
            )
        previous_entry = self._read_published_entry(entry_id)
        now = _utc_now()
        patch = request.model_dump(mode="json", exclude_none=True, exclude={"reason"})
        payload = previous_entry.model_dump(mode="json")
        payload.update(patch)
        payload.update(
            {
                "id": entry_id,
                "trust_state": "published",
                "author_type": "human",
                "author": user,
                "updated": now,
            }
        )
        context = self._base_context(user=user, operation="propose_update", payload=payload)
        context["previous_entry"] = previous_entry
        result = run_pipeline(context, self._pipeline())
        return _write_result(result, include_proposed_id=False)

    def _base_context(
        self,
        *,
        user: str,
        operation: str,
        payload: dict[str, Any],
    ) -> MiddlewareContext:
        # P8 V1 trusts the intranet boundary plus X-KB-User. This is not real
        # authentication; token/session auth must replace it before wider exposure.
        allocator = self.id_allocator or IDAllocator(self.kb_root / "indexes" / "ids.sqlite")
        if operation == "propose_entry":
            try:
                allocator.rebuild_from_kb(self.kb_root)
            except ValueError as exc:
                raise WebApiError(
                    "E_SCHEMA",
                    "id allocator rebuild failed",
                    "id_allocator",
                ) from exc

        context: MiddlewareContext = {
            "auth": {"user": user, "author_type": "human"},
            "operation": operation,
            "payload": payload,
            "repo_root": self.repo_root,
            "kb_root": self.kb_root,
            "id_allocator": allocator,
            "claimed_change_scopes": [WEB_WRITE_SCOPE],
        }
        if self.audit_path is not None:
            context["audit_path"] = self.audit_path
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
            _require_web_staging_target,
            persist(),
            audit_append(),
        )

    def _read_published_entry(self, entry_id: str) -> Entry:
        path = _state_entry_path(self.kb_root, PUBLISHED_DIR, entry_id)
        if not path.is_file():
            raise WebApiError("E_SCHEMA", f"entry not found: {entry_id}", "id", 404)
        try:
            item = read_valid_entry_file(
                self.kb_root,
                PUBLISHED_DIR,
                path,
                context="web api update read",
            )
        except ValueError as exc:
            LOGGER.warning("web api update invalid entry source for %s: %s", entry_id, exc)
            raise WebApiError("E_SCHEMA", "invalid entry source", "id") from exc
        if item is None:
            raise WebApiError("E_SCHEMA", f"entry is unreadable or invalid: {entry_id}", "id", 404)
        return item.entry

    def _pending_entry_exists(self, entry_id: str) -> bool:
        path = _state_entry_path(self.kb_root, PENDING_DIR, entry_id)
        return path.is_file()


@dataclass(frozen=True, slots=True)
class WebReviewService:
    """Human Web review facade backed by the Phase 5 review service."""

    repo_root: Path
    kb_root: Path
    roles_config: RolesConfig
    audit_path: Path | None = None

    def review_queue_for_web(self, *, user: str) -> dict[str, Any]:
        self._require_queue_permission(user)
        queue = list_review_queue(
            kb_root=self.kb_root,
            repo_root=self.repo_root,
            audit_path=self.audit_path,
        )
        return _review_queue_to_dict(queue)

    def approve_from_web(
        self,
        entry_id: str,
        request: WebReviewDecisionRequest,
        *,
        user: str,
    ) -> dict[str, Any]:
        _validate_kb_id(entry_id)
        result = approve_staging_entry(
            kb_root=self.kb_root,
            repo_root=self.repo_root,
            roles_config=self.roles_config,
            reviewer=user,
            entry_id=entry_id,
            note=request.note,
            audit_path=self.audit_path,
        )
        return _review_result_to_dict(result, decision="approve")

    def reject_from_web(
        self,
        entry_id: str,
        request: WebReviewDecisionRequest,
        *,
        user: str,
    ) -> dict[str, Any]:
        _validate_kb_id(entry_id)
        result = reject_staging_entry(
            kb_root=self.kb_root,
            repo_root=self.repo_root,
            roles_config=self.roles_config,
            reviewer=user,
            entry_id=entry_id,
            note=request.note,
            audit_path=self.audit_path,
        )
        return _review_result_to_dict(result, decision="reject")

    def _require_queue_permission(self, user: str) -> None:
        try:
            _role, permissions = self.roles_config.permissions_for_user(user)
        except KeyError as exc:
            raise WebApiError("E_PERM", f"unknown reviewer: {user}", "reviewer", 403) from exc
        if ADMIN_PERMISSION in permissions:
            return
        if "review_light" in permissions or "review_heavy" in permissions:
            return
        raise WebApiError(
            "E_PERM",
            "permission required: review_light or review_heavy",
            "auth.permissions",
            403,
        )


def build_scope(
    *,
    module: str | None = None,
    entry_type: EntryTypeParam | None = None,
    error_code: str | None = None,
    claim_type: ClaimTypeParam | None = None,
    min_support: SupportParam | None = None,
    exclude_stale: bool = False,
    status: Literal["published"] | None = None,
) -> SearchScope:
    scope: SearchScope = {}
    if module:
        scope["module"] = module
    if entry_type:
        scope["entry_type"] = entry_type
    if error_code:
        scope["error_code"] = error_code
    if claim_type:
        scope["claim_type"] = claim_type
    if min_support:
        scope["min_support"] = min_support
    if exclude_stale:
        scope["exclude_stale"] = True
    if status:
        scope["status"] = status
    return scope


def _published_entry_path(kb_root: Path, entry_id: str) -> Path:
    return _state_entry_path(kb_root, PUBLISHED_DIR, entry_id)


def _published_root(kb_root: Path) -> Path:
    return _state_root(kb_root, PUBLISHED_DIR)


def _state_entry_path(kb_root: Path, dirname: Literal["entries", "staging"], entry_id: str) -> Path:
    _validate_kb_id(entry_id)
    base = _state_root(kb_root, dirname)
    path = (base / f"{entry_id}.md").resolve()
    if not path.is_relative_to(base):
        raise WebApiError("E_SCHEMA", f"entry path escaped {dirname} directory", "id")
    return path


def _state_root(kb_root: Path, dirname: Literal["entries", "staging"]) -> Path:
    root = kb_root.resolve()
    source_path = root / dirname
    if source_path.exists() and source_path.is_symlink():
        raise WebApiError("E_SCHEMA", f"{dirname} directory must not be a symlink", "kb_root")
    resolved = source_path.resolve()
    if not resolved.is_relative_to(root):
        raise WebApiError("E_SCHEMA", f"{dirname} directory escapes kb root", "kb_root")
    return resolved


def _validate_kb_id(entry_id: str) -> None:
    if not KB_ID_RE.fullmatch(entry_id):
        raise WebApiError("E_SCHEMA", "id must match KB-{year}-{NNNN}", "id")


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


def _graph_node(entry: Entry) -> dict[str, Any]:
    node = _entry_summary(entry)
    node["tags"] = entry.tags
    node["updated"] = entry.updated
    return node


def _write_result(
    result: MiddlewareResult,
    *,
    include_proposed_id: bool,
) -> dict[str, Any]:
    context = result["context"]
    error = result["error"]
    response: dict[str, Any] = {
        "ok": error is None,
        "validation_errors": [
            _issue_to_dict(issue) for issue in context.get("validation_errors", [])
        ],
        "validation_warnings": [
            _issue_to_dict(issue) for issue in context.get("validation_warnings", [])
        ],
    }
    if error is not None:
        response["error"] = _api_error_to_issue(error)
        response["validation_errors"].append(response["error"])
        return response

    entry = context.get("entry")
    if entry is not None:
        response["id"] = entry.id
    if include_proposed_id:
        proposed_id = context.get("allocated_id") or (entry.id if entry is not None else None)
        if proposed_id is not None:
            response["proposed_id"] = proposed_id
    target_dir = context.get("target_dir")
    response["target_dir"] = target_dir
    response["status"] = "auto_published" if target_dir == PUBLISHED_DIR else "pending"
    if "review_level" in context:
        response["review_level"] = context["review_level"]
    return response


def _failed_write_result(error: ApiError) -> dict[str, Any]:
    issue = _api_error_to_issue(error)
    return {
        "ok": False,
        "error": issue,
        "validation_errors": [issue],
        "validation_warnings": [],
    }


def _review_queue_to_dict(queue: ReviewQueue) -> dict[str, Any]:
    return {
        "items": [
            {
                "entry_id": item.entry_id,
                "title": item.title,
                "module": item.module,
                "entry_type": item.entry_type,
                "claim_type": item.claim_type,
                "support_strength": item.support_strength,
                "review_level": item.review_level,
                "updated": item.updated,
                "path": item.path,
            }
            for item in queue.items
        ],
        "backlog_count": queue.backlog_count,
        "backlog_warning": queue.backlog_warning,
        "skipped_files": queue.skipped_files,
    }


def _review_result_to_dict(
    result: ReviewOperationResult,
    *,
    decision: str,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": result.ok,
        "decision": decision,
        "validation_errors": [],
        "validation_warnings": [],
    }
    if result.review_level is not None:
        response["review_level"] = result.review_level
    if result.entry is not None:
        response["id"] = result.entry.id
        response["status"] = result.entry.trust_state.value
    if result.target_path is not None:
        response["target_path"] = result.target_path.name
    if result.warning is not None:
        warning = _review_api_error_to_issue(
            result.warning,
            decision=decision,
            severity="warning",
        )
        response["warning"] = warning
        response["validation_warnings"].append(warning)
    if result.error is not None:
        error = _review_api_error_to_issue(
            result.error,
            decision=decision,
            severity="error",
        )
        response["error"] = error
        response["validation_errors"].append(error)
    return response


def _require_web_staging_target(context: MiddlewareContext) -> MiddlewareResult:
    if context.get("target_dir") != PENDING_DIR:
        return fail(
            context,
            ApiError(
                "E_SCHEMA",
                "web writes must route to staging",
                "target_dir",
            ),
        )
    return ok(context)


def write_status_code(result: dict[str, Any], *, success_status: int = 200) -> int:
    if result.get("ok") is True:
        return success_status
    error = result.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if code == "E_PERM":
        return 403
    if code == "E_DUP":
        return 409
    return 400


def _api_error_to_issue(error: ApiError) -> dict[str, Any]:
    return {"code": error.code, "field": error.field or "", "message": error.message}


def _review_api_error_to_issue(
    error: ApiError,
    *,
    decision: str,
    severity: str,
) -> dict[str, Any]:
    LOGGER.warning(
        "web review %s returned %s from P5: code=%s field=%s message=%s",
        decision,
        severity,
        error.code,
        error.field,
        error.message,
    )
    issue = _api_error_to_issue(error)
    if _review_error_needs_redaction(error):
        issue["message"] = _public_review_error_message(error)
    return issue


def _review_error_needs_redaction(error: ApiError) -> bool:
    field = error.field or ""
    return field in REVIEW_STORAGE_FIELDS or PATH_LIKE_MESSAGE_RE.search(error.message) is not None


def _public_review_error_message(error: ApiError) -> str:
    field = error.field or ""
    return REVIEW_PUBLIC_MESSAGES.get(field, "review operation failed")


def _issue_to_dict(issue: object) -> dict[str, Any]:
    code = getattr(issue, "code", "")
    return {
        "code": getattr(code, "value", str(code)),
        "field": getattr(issue, "field", ""),
        "message": getattr(issue, "message", ""),
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
