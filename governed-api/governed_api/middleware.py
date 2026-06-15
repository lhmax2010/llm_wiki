"""V1 Governed API middleware implementations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from core.id_allocator import IDAllocator
from core.models import Entry, TrustState
from core.storage import write_entry
from core.validation import validate_entry
from governed_api.audit import append_audit_record, build_audit_record
from governed_api.roles import RolesConfig
from governed_api.types import (
    ApiError,
    Middleware,
    MiddlewareContext,
    MiddlewareResult,
    ReviewLevel,
    TargetDir,
    fail,
    ok,
)

PROVISIONAL_ID = "KB-1000-0000"
CREATE_OPERATIONS = {"create", "propose", "propose_entry"}
UPDATE_OPERATIONS = {"update", "propose_update"}
CONTRIBUTOR_PLUS = {"contributor", "reviewer", "admin"}
VALID_REVIEW_LEVELS = {"auto", "light", "heavy"}
AUTO_SCOPES = {
    "typo",
    "punctuation",
    "markdown_format",
    "link_fix",
    "tag_alias_normalization",
}
LIGHT_SCOPES = AUTO_SCOPES | {
    "wording",
    "add_evidence",
    "code_binding_noncritical",
    "new_alias",
}
HEAVY_SCOPES = {
    "new_defect_case",
    "new_triage_rule",
    "claim_type_change",
    "evidence_change",
    "root_cause_change",
    "solution_change",
    "criterion_change",
    "code_binding_critical",
    "section_credibility_change",
    "agent_hypothesis",
    "static_inference",
}
AUTO_FIELDS = {"tags", "updated"}
LIGHT_FIELDS = {
    "aliases",
    "title",
    "module",
    "symptom_keywords",
    "error_codes",
    "log_signatures",
    "versions_affected",
    "hardware",
    "severity",
    "related",
}
HEAVY_FIELDS = {
    "id",
    "schema_version",
    "entry_type",
    "trust_state",
    "author_type",
    "section_credibility",
    "inferred_fields",
    "body",
    "source_refs",
    "trigger",
}
TRUST_STATE_BY_TARGET_DIR: dict[TargetDir, TrustState] = {
    "research": TrustState.RESEARCH,
    "drafts": TrustState.DRAFT,
    "staging": TrustState.PENDING,
    "entries": TrustState.PUBLISHED,
}


def auth_context(roles_config: RolesConfig) -> Middleware:
    def _auth_context(context: MiddlewareContext) -> MiddlewareResult:
        auth = dict(context.get("auth", {}))
        user = auth.get("user")
        if not isinstance(user, str) or not user:
            return fail(context, ApiError("E_PERM", "auth.user is required", "auth.user"))

        role = auth.get("role")
        if role is None:
            role = roles_config.role_for_user(user)
        if not isinstance(role, str) or not role:
            return fail(context, ApiError("E_PERM", "auth.role is required", "auth.role"))

        try:
            permissions = roles_config.permissions_for_role(role)
        except KeyError:
            return fail(context, ApiError("E_PERM", f"unknown role: {role}", "auth.role"))

        next_context: MiddlewareContext = context.copy()
        next_context["auth"] = {"user": user, "role": role, "permissions": permissions}
        return ok(next_context)

    return _auth_context


def schema_validate(*, allow_id_allocation: bool = True) -> Middleware:
    def _schema_validate(context: MiddlewareContext) -> MiddlewareResult:
        payload = dict(context["payload"])
        id_was_missing = "id" not in payload
        if id_was_missing:
            if allow_id_allocation and context["operation"] in CREATE_OPERATIONS:
                payload["id"] = PROVISIONAL_ID
            else:
                return fail(context, ApiError("E_SCHEMA", "payload.id is required", "payload.id"))
        try:
            entry = Entry.model_validate(payload)
        except ValidationError as exc:
            return fail(
                context,
                ApiError(
                    code="E_SCHEMA",
                    field="payload",
                    message="payload failed Entry schema validation",
                    details=exc.errors(),
                ),
            )

        next_context: MiddlewareContext = context.copy()
        next_context["entry"] = entry
        next_context["payload"] = payload
        next_context["id_was_missing"] = id_was_missing
        next_context.setdefault("validation_errors", [])
        next_context.setdefault("validation_warnings", [])
        return ok(next_context)

    return _schema_validate


def evidence_validate() -> Middleware:
    def _evidence_validate(context: MiddlewareContext) -> MiddlewareResult:
        entry = context.get("entry")
        if entry is None:
            return fail(context, ApiError("E_SCHEMA", "context.entry is required", "entry"))
        repo_root = context.get("repo_root")
        kb_root = context.get("kb_root")
        if repo_root is None:
            return fail(context, ApiError("E_SCHEMA", "repo_root is required", "repo_root"))
        if kb_root is None:
            return fail(context, ApiError("E_SCHEMA", "kb_root is required", "kb_root"))

        report = validate_entry(
            entry,
            repo_root=repo_root,
            kb_root=kb_root,
            entry_path=context.get("entry_path"),
        )
        next_context: MiddlewareContext = context.copy()
        next_context["entry"] = report.entry
        next_context["validation_errors"] = report.errors
        next_context["validation_warnings"] = report.warnings
        if report.errors:
            return fail(
                next_context,
                ApiError(
                    code="E_VALIDATION",
                    field="validation_errors",
                    message="entry validation failed",
                    details=report.errors,
                ),
            )
        return ok(next_context)

    return _evidence_validate


def classify_write_route() -> Middleware:
    def _classify_write_route(context: MiddlewareContext) -> MiddlewareResult:
        operation = context["operation"]
        role = context["auth"]["role"]
        review_level = _classify_review_level(context, operation, role)
        target_dir: TargetDir = "entries" if review_level == "auto" else "staging"
        next_context: MiddlewareContext = context.copy()
        next_context["review_level"] = review_level
        next_context["target_dir"] = target_dir
        return ok(next_context)

    return _classify_write_route


def review_route() -> Middleware:
    def _review_route(context: MiddlewareContext) -> MiddlewareResult:
        review_level = context.get("review_level")
        target_dir = context.get("target_dir")
        entry = context.get("entry")
        if review_level not in VALID_REVIEW_LEVELS:
            return fail(context, ApiError("E_SCHEMA", "invalid review_level", "review_level"))
        if target_dir not in TRUST_STATE_BY_TARGET_DIR:
            return fail(context, ApiError("E_SCHEMA", "invalid target_dir", "target_dir"))
        if entry is None:
            return fail(context, ApiError("E_SCHEMA", "context.entry is required", "entry"))

        next_context: MiddlewareContext = context.copy()
        next_context["entry"] = entry.model_copy(
            update={"trust_state": TRUST_STATE_BY_TARGET_DIR[target_dir]}
        )
        return ok(next_context)

    return _review_route


def persist() -> Middleware:
    def _persist(context: MiddlewareContext) -> MiddlewareResult:
        entry = context.get("entry")
        kb_root = context.get("kb_root")
        repo_root = context.get("repo_root")
        target_dir = context.get("target_dir")
        allocator = context.get("id_allocator")
        if entry is None:
            return fail(context, ApiError("E_SCHEMA", "context.entry is required", "entry"))
        if kb_root is None:
            return fail(context, ApiError("E_SCHEMA", "kb_root is required", "kb_root"))
        if repo_root is None:
            return fail(context, ApiError("E_SCHEMA", "repo_root is required", "repo_root"))
        if target_dir is None:
            return fail(context, ApiError("E_SCHEMA", "target_dir is required", "target_dir"))
        if allocator is None:
            return fail(context, ApiError("E_SCHEMA", "id_allocator is required", "id_allocator"))
        if not isinstance(allocator, IDAllocator):
            return fail(
                context, ApiError("E_SCHEMA", "id_allocator has invalid type", "id_allocator")
            )

        allocated_id: str | None = None
        if context.get("id_was_missing") or entry.id == PROVISIONAL_ID:
            allocated_id = allocator.allocate()
            entry = entry.model_copy(update={"id": allocated_id})

        path = kb_root / target_dir / f"{entry.id}.md"
        report = validate_entry(entry, repo_root=repo_root, kb_root=kb_root, entry_path=path)
        next_context: MiddlewareContext = context.copy()
        next_context["entry"] = report.entry
        next_context["validation_errors"] = report.errors
        next_context["validation_warnings"] = report.warnings
        if allocated_id is not None:
            next_context["allocated_id"] = allocated_id
        if report.errors:
            return fail(
                next_context,
                ApiError(
                    code="E_VALIDATION",
                    field="validation_errors",
                    message="entry validation failed before persist",
                    details=report.errors,
                ),
            )

        write_entry(path, report.entry)
        next_context["persisted_path"] = path
        return ok(next_context)

    return _persist


def audit_append() -> Middleware:
    def _audit_append(context: MiddlewareContext) -> MiddlewareResult:
        kb_root = context.get("kb_root")
        if kb_root is None:
            return fail(context, ApiError("E_SCHEMA", "kb_root is required", "kb_root"))
        if "persisted_path" not in context:
            return fail(
                context, ApiError("E_SCHEMA", "persisted_path is required", "persisted_path")
            )

        audit_path = context.get("audit_path", kb_root / "indexes" / "audit.jsonl")
        record = build_audit_record(context)
        append_audit_record(audit_path, record)
        next_context: MiddlewareContext = context.copy()
        next_context["audit_path"] = audit_path
        next_context["audit_record"] = record
        return ok(next_context)

    return _audit_append


def _classify_review_level(
    context: MiddlewareContext,
    operation: str,
    role: str,
) -> ReviewLevel:
    if operation in CREATE_OPERATIONS:
        return "heavy"
    if role not in CONTRIBUTOR_PLUS:
        return "heavy"
    if operation not in UPDATE_OPERATIONS:
        return "heavy"

    scopes = set(context.get("change_scopes", []))
    if scopes:
        if scopes & HEAVY_SCOPES:
            return "heavy"
        if scopes <= AUTO_SCOPES:
            return "auto"
        if scopes <= LIGHT_SCOPES:
            return "light"
        return "heavy"

    changed_fields = _changed_fields(context)
    if not changed_fields:
        return "heavy"
    if changed_fields & HEAVY_FIELDS:
        return "heavy"
    if _credibility_change_is_heavy(context):
        return "heavy"
    if _code_binding_change_is_heavy(context):
        return "heavy"
    changed_without_special = changed_fields - {"credibility", "code_binding"}
    if "credibility" in changed_fields or "code_binding" in changed_fields:
        return "light"
    if changed_without_special <= AUTO_FIELDS:
        return "auto"
    if changed_without_special <= (AUTO_FIELDS | LIGHT_FIELDS):
        return "light"
    return "heavy"


def _changed_fields(context: MiddlewareContext) -> set[str]:
    explicit = context.get("changed_fields")
    if explicit is not None:
        return set(explicit)

    entry = context.get("entry")
    if entry is None:
        return set()
    new_payload = entry.model_dump(mode="json")
    previous_payload = _normalized_previous_payload(context)
    if previous_payload is None:
        return set()
    return {
        field
        for field in set(previous_payload) | set(new_payload)
        if previous_payload.get(field) != new_payload.get(field)
    }


def _credibility_change_is_heavy(context: MiddlewareContext) -> bool:
    changed_fields = _changed_fields(context)
    if "credibility" not in changed_fields:
        return False
    old, new = _old_new_mapping(context, "credibility")
    if not old or not new:
        return True
    old_without_evidence = {key: value for key, value in old.items() if key != "evidence"}
    new_without_evidence = {key: value for key, value in new.items() if key != "evidence"}
    if old_without_evidence != new_without_evidence:
        return True
    old_evidence = _as_list(old.get("evidence"))
    new_evidence = _as_list(new.get("evidence"))
    return not _is_prefix(old_evidence, new_evidence)


def _code_binding_change_is_heavy(context: MiddlewareContext) -> bool:
    changed_fields = _changed_fields(context)
    if "code_binding" not in changed_fields:
        return False
    old, new = _old_new_mapping(context, "code_binding")
    if old is None or new is None:
        return True
    critical_old = {
        key: value for key, value in old.items() if key not in {"stale", "stale_reason"}
    }
    critical_new = {
        key: value for key, value in new.items() if key not in {"stale", "stale_reason"}
    }
    return critical_old != critical_new


def _old_new_mapping(
    context: MiddlewareContext,
    field: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    entry = context.get("entry")
    if entry is None:
        return None, None
    previous_payload = _normalized_previous_payload(context)
    new_value = entry.model_dump(mode="json").get(field)
    old_value = previous_payload.get(field) if previous_payload is not None else None
    return _as_mapping(old_value), _as_mapping(new_value)


def _normalized_previous_payload(context: MiddlewareContext) -> dict[str, Any] | None:
    previous_entry = context.get("previous_entry")
    if previous_entry is not None:
        return previous_entry.model_dump(mode="json")
    previous_payload = context.get("previous_payload")
    if previous_payload is None:
        return None
    try:
        return Entry.model_validate(previous_payload).model_dump(mode="json")
    except ValidationError:
        return previous_payload


def _as_mapping(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _is_prefix(prefix: Iterable[object], value: list[object]) -> bool:
    prefix_list = list(prefix)
    return len(prefix_list) <= len(value) and value[: len(prefix_list)] == prefix_list
