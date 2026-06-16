from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from governed_api.middleware import (
    PROVISIONAL_ID,
    audit_append,
    auth_context,
    classify_write_route,
    evidence_validate,
    persist,
    review_route,
    schema_validate,
)
from governed_api.pipeline import run_pipeline
from governed_api.roles import RolesConfig
from governed_api.types import MiddlewareContext

from core.errors import IssueCode
from core.validation import ValidationReport
from tests.governed_api.helpers import entry_payload


def test_auth_context_adds_permissions(
    make_context: Callable[..., MiddlewareContext], roles_config: RolesConfig
) -> None:
    context = make_context(include_roots=False)
    context["auth"] = {"user": "alice", "role": "contributor"}

    result = auth_context(roles_config)(context)

    assert result["ok"]
    assert result["context"]["auth"]["permissions"] == ["read_published", "propose_entry"]


def test_auth_context_can_resolve_role_from_users(
    make_context: Callable[..., MiddlewareContext], roles_config: RolesConfig
) -> None:
    context = make_context(include_roots=False)
    context["auth"] = {"user": "reviewer"}

    result = auth_context(roles_config)(context)

    assert result["ok"]
    assert result["context"]["auth"]["role"] == "reviewer"


def test_auth_context_rejects_missing_user_role_mismatch_and_unknown_user(
    make_context: Callable[..., MiddlewareContext], roles_config: RolesConfig
) -> None:
    missing_user = make_context(include_roots=False)
    missing_user["auth"] = {"user": "", "role": "contributor"}
    role_mismatch = make_context(include_roots=False)
    role_mismatch["auth"] = {"user": "reader", "role": "admin"}
    unknown_user = make_context(include_roots=False)
    unknown_user["auth"] = {"user": "mallory", "role": "admin"}
    missing_result = auth_context(roles_config)(missing_user)
    mismatch_result = auth_context(roles_config)(role_mismatch)
    unknown_result = auth_context(roles_config)(unknown_user)

    assert missing_result["error"] is not None
    assert missing_result["error"].field == "auth.user"
    assert mismatch_result["error"] is not None
    assert mismatch_result["error"].field == "auth.role"
    assert unknown_result["error"] is not None
    assert unknown_result["error"].field == "auth.user"


def test_auth_context_enforces_operation_permission(
    make_context: Callable[..., MiddlewareContext], roles_config: RolesConfig
) -> None:
    reader = make_context(include_roots=False, user="reader", role="reader")
    reviewer = make_context(include_roots=False, user="reviewer", role="reviewer")

    denied = auth_context(roles_config)(reader)
    allowed = auth_context(roles_config)(reviewer)

    assert not denied["ok"]
    assert denied["error"] is not None
    assert denied["error"].code == "E_PERM"
    assert denied["error"].field == "auth.permissions"
    assert allowed["ok"]
    assert "propose_entry" in allowed["context"]["auth"]["permissions"]


def test_auth_context_blocks_agent_research_write_operations(
    make_context: Callable[..., MiddlewareContext], roles_config: RolesConfig
) -> None:
    context = make_context(
        include_roots=False,
        operation="create_research",
        user="reviewer",
        role="reviewer",
    )
    context["auth"]["author_type"] = "agent"

    result = auth_context(roles_config)(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_PERM"
    assert result["error"].field == "auth.author_type"


def test_schema_validate_allows_create_payload_without_id(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(payload=entry_payload(entry_id=None))

    result = schema_validate()(context)

    assert result["ok"]
    assert result["context"]["entry"].id == PROVISIONAL_ID
    assert result["context"]["id_was_missing"] is True


def test_schema_validate_rejects_create_payload_with_self_declared_id(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(payload=entry_payload(entry_id="KB-2026-0999"))

    result = schema_validate()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "payload.id"


def test_schema_validate_requires_id_for_update(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(payload=entry_payload(entry_id=None), operation="update")

    result = schema_validate()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "payload.id"


def test_schema_validate_reports_pydantic_errors(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    payload = entry_payload(entry_id=None)
    payload["schema_version"] = 2
    context = make_context(payload=payload)

    result = schema_validate()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_SCHEMA"
    assert result["error"].field == "payload"


def test_evidence_validate_requires_repo_and_kb_roots(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(include_roots=False)
    context = schema_validate()(context)["context"]

    result = evidence_validate()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "repo_root"


def test_evidence_validate_requires_entry_and_kb_root(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    no_entry = make_context()
    no_entry.pop("entry", None)
    no_kb = make_context()
    no_kb = schema_validate()(no_kb)["context"]
    no_kb.pop("kb_root")
    no_entry_result = evidence_validate()(no_entry)
    no_kb_result = evidence_validate()(no_kb)

    assert no_entry_result["error"] is not None
    assert no_entry_result["error"].field == "entry"
    assert no_kb_result["error"] is not None
    assert no_kb_result["error"].field == "kb_root"


def test_evidence_validate_passes_roots_to_core_validation(
    make_context: Callable[..., MiddlewareContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context()
    context = schema_validate()(context)["context"]
    calls: list[tuple[Path, Path]] = []

    def fake_validate_entry(*args: object, **kwargs: object) -> ValidationReport:
        calls.append((kwargs["repo_root"], kwargs["kb_root"]))  # type: ignore[arg-type]
        entry = args[0]
        return SimpleNamespace(entry=entry, errors=[], warnings=[])  # type: ignore[return-value]

    monkeypatch.setattr("governed_api.middleware.validate_entry", fake_validate_entry)

    result = evidence_validate()(context)

    assert result["ok"]
    assert calls == [(context["repo_root"], context["kb_root"])]


def test_evidence_validate_surfaces_core_errors(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(
        payload=entry_payload(entry_id=None, evidence=[{"type": "human_note"}]),
    )
    context = schema_validate()(context)["context"]

    result = evidence_validate()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_SCHEMA"
    assert result["context"]["validation_errors"][0].code == IssueCode.E_SCHEMA


def test_create_is_heavy_and_targets_staging(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context()
    context = schema_validate()(context)["context"]
    context = evidence_validate()(context)["context"]

    result = classify_write_route()(context)

    assert result["ok"]
    assert result["context"]["review_level"] == "heavy"
    assert result["context"]["target_dir"] == "staging"


def test_update_without_diff_is_conservative_heavy(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(operation="update", payload=entry_payload(trust_state="published"))
    context = schema_validate()(context)["context"]
    context = evidence_validate()(context)["context"]

    result = classify_write_route()(context)

    assert result["context"]["review_level"] == "heavy"


def test_update_auto_scope_can_auto_publish(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    old_payload = entry_payload(trust_state="published", tags=[])
    new_payload = entry_payload(trust_state="published", tags=["normalized"])
    context = make_context(operation="update", payload=new_payload)
    context["previous_payload"] = old_payload
    context["change_scopes"] = ["typo", "link_fix"]
    context = schema_validate()(context)["context"]
    context = evidence_validate()(context)["context"]

    result = classify_write_route()(context)

    assert result["context"]["review_level"] == "auto"
    assert result["context"]["target_dir"] == "entries"


def test_update_scope_rules_are_conservative(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    old_payload = entry_payload(trust_state="published", aliases=[])
    new_payload = entry_payload(trust_state="published", aliases=["decoder"])
    heavy = make_context(operation="update", payload=new_payload)
    heavy["previous_payload"] = old_payload
    heavy["change_scopes"] = ["claim_type_change"]
    light = make_context(operation="update", payload=new_payload)
    light["previous_payload"] = old_payload
    light["change_scopes"] = ["wording"]
    unknown = make_context(operation="update", payload=new_payload)
    unknown["previous_payload"] = old_payload
    unknown["change_scopes"] = ["surprising_change"]
    reader = make_context(
        operation="update", payload=entry_payload(trust_state="published"), role="reader"
    )
    reader["change_scopes"] = ["typo"]

    for context in (heavy, light, unknown, reader):
        context = schema_validate()(context)["context"]
        context = evidence_validate()(context)["context"]
        result = classify_write_route()(context)
        if context["auth"]["role"] == "reader":
            assert result["context"]["review_level"] == "heavy"
        elif context.get("change_scopes") == ["wording"]:
            assert result["context"]["review_level"] == "light"
        else:
            assert result["context"]["review_level"] == "heavy"


def test_self_reported_diff_cannot_downgrade_actual_heavy_change(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    old_payload = entry_payload(trust_state="published", claim_type="observation")
    new_payload = entry_payload(
        trust_state="published",
        claim_type="fact",
        evidence=[{"type": "spec", "uri": "spec://decoder", "version": "v1"}],
    )
    context = make_context(operation="update", payload=new_payload)
    context["previous_payload"] = old_payload
    context["change_scopes"] = ["typo"]
    context["changed_fields"] = ["tags"]
    context = schema_validate()(context)["context"]
    context = evidence_validate()(context)["context"]

    result = classify_write_route()(context)

    assert result["context"]["review_level"] == "heavy"
    assert result["context"]["target_dir"] == "staging"
    assert "credibility" in result["context"]["actual_changed_fields"]


def test_update_add_evidence_is_light_not_auto(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    old_payload = entry_payload(trust_state="published")
    new_payload = entry_payload(
        trust_state="published",
        evidence=[
            {"type": "human_note", "excerpt": "Observed by reviewer."},
            {"type": "human_note", "excerpt": "Second reviewer confirmed."},
        ],
    )
    context = make_context(operation="update", payload=new_payload)
    context["previous_payload"] = old_payload
    context = schema_validate()(context)["context"]
    context = evidence_validate()(context)["context"]

    result = classify_write_route()(context)

    assert result["context"]["review_level"] == "light"
    assert result["context"]["target_dir"] == "staging"


def test_update_claim_type_change_is_heavy(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    old_payload = entry_payload(trust_state="published", claim_type="observation")
    new_payload = entry_payload(
        trust_state="published",
        claim_type="fact",
        evidence=[{"type": "spec", "uri": "spec://decoder", "version": "v1"}],
    )
    context = make_context(operation="update", payload=new_payload)
    context["previous_payload"] = old_payload
    context = schema_validate()(context)["context"]
    context = evidence_validate()(context)["context"]

    result = classify_write_route()(context)

    assert result["context"]["review_level"] == "heavy"


def test_update_changed_fields_auto_light_and_heavy(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    auto = make_context(
        operation="update",
        payload=entry_payload(trust_state="published", tags=["doc"]),
    )
    auto["previous_payload"] = entry_payload(trust_state="published", tags=[])
    light = make_context(
        operation="update",
        payload=entry_payload(trust_state="published", aliases=["decoder"]),
    )
    light["previous_payload"] = entry_payload(trust_state="published", aliases=[])
    changed_body = f"{entry_payload(trust_state='published')['body']}\n\n## 备注\nchanged\n"
    heavy = make_context(
        operation="update",
        payload=entry_payload(trust_state="published", body=changed_body),
    )
    heavy["previous_payload"] = entry_payload(trust_state="published")

    for context, expected in ((auto, "auto"), (light, "light"), (heavy, "heavy")):
        context = schema_validate()(context)["context"]
        context = evidence_validate()(context)["context"]
        result = classify_write_route()(context)
        assert result["context"]["review_level"] == expected


def test_update_code_binding_noncritical_is_light_critical_is_heavy(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    old_payload = entry_payload(trust_state="published")
    old_payload["code_binding"] = {"stale": False}
    noncritical_payload = entry_payload(trust_state="published")
    noncritical_payload["code_binding"] = {"stale": True}
    critical_payload = entry_payload(trust_state="published")
    critical_payload["code_binding"] = {"paths": ["src/decoder.c"]}

    noncritical = make_context(operation="update", payload=noncritical_payload)
    noncritical["previous_payload"] = old_payload
    critical = make_context(operation="update", payload=critical_payload)
    critical["previous_payload"] = old_payload

    for context, expected in ((noncritical, "light"), (critical, "heavy")):
        context = schema_validate()(context)["context"]
        context = evidence_validate()(context)["context"]
        result = classify_write_route()(context)
        assert result["context"]["review_level"] == expected


def test_review_route_sets_trust_state_from_target_dir(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(operation="update", payload=entry_payload(trust_state="published"))
    context = schema_validate()(context)["context"]
    context["review_level"] = "heavy"
    context["target_dir"] = "staging"

    result = review_route()(context)

    assert result["ok"]
    assert result["context"]["entry"].trust_state == "pending"


def test_review_route_rejects_invalid_context(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    invalid_level = make_context()
    invalid_level = schema_validate()(invalid_level)["context"]
    invalid_level["review_level"] = "wild"  # type: ignore[typeddict-item]
    invalid_level["target_dir"] = "staging"
    invalid_target = make_context()
    invalid_target = schema_validate()(invalid_target)["context"]
    invalid_target["review_level"] = "heavy"
    invalid_target["target_dir"] = "elsewhere"  # type: ignore[typeddict-item]
    invalid_level_result = review_route()(invalid_level)
    invalid_target_result = review_route()(invalid_target)

    assert invalid_level_result["error"] is not None
    assert invalid_level_result["error"].field == "review_level"
    assert invalid_target_result["error"] is not None
    assert invalid_target_result["error"].field == "target_dir"


def test_persist_allocates_id_writes_entry_and_audit(
    make_context: Callable[..., MiddlewareContext],
    roles_config: RolesConfig,
) -> None:
    context = make_context(payload=entry_payload(entry_id=None, trust_state="pending"))
    result = run_pipeline(
        context,
        [
            auth_context(roles_config),
            schema_validate(),
            evidence_validate(),
            classify_write_route(),
            review_route(),
            persist(),
            audit_append(),
        ],
    )

    assert result["ok"], result["error"]
    final_context = result["context"]
    assert final_context["allocated_id"] == "KB-2026-0001"
    assert final_context["entry"].id == "KB-2026-0001"
    persisted_path = final_context["persisted_path"]
    assert persisted_path == final_context["kb_root"] / "staging" / "KB-2026-0001.md"
    assert persisted_path.exists()
    assert "KB-2026-0001" in persisted_path.read_text(encoding="utf-8")

    audit_lines = (
        (final_context["kb_root"] / "indexes" / "audit.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    audit = json.loads(audit_lines[0])
    assert audit["user"] == "alice"
    assert audit["operation"] == "create"
    assert audit["entry_id"] == "KB-2026-0001"
    assert audit["target_dir"] == "staging"
    assert audit["path"] == "staging/KB-2026-0001.md"
    assert audit["review_level"] == "heavy"
    assert not Path(audit["path"]).is_absolute()


def test_persist_requires_context_dependencies(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context()
    context = schema_validate()(context)["context"]
    context["target_dir"] = "staging"
    context.pop("id_allocator")

    result = persist()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "id_allocator"


def test_persist_revalidates_target_dir_before_write(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context(payload=entry_payload(entry_id=None, trust_state="pending"))
    context = schema_validate()(context)["context"]
    context["target_dir"] = "entries"

    result = persist()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_SCHEMA"
    assert result["context"]["allocated_id"] == "KB-2026-0001"
    assert not (context["kb_root"] / "entries" / "KB-2026-0001.md").exists()


def test_audit_append_requires_persisted_path(
    make_context: Callable[..., MiddlewareContext],
) -> None:
    context = make_context()

    result = audit_append()(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "persisted_path"


def test_audit_failure_rolls_back_persisted_entry(
    make_context: Callable[..., MiddlewareContext],
    roles_config: RolesConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_append(*args: object, **kwargs: object) -> None:
        raise PermissionError("audit blocked")

    monkeypatch.setattr("governed_api.middleware.append_audit_record", fail_append)
    context = make_context(payload=entry_payload(entry_id=None, trust_state="pending"))

    result = run_pipeline(
        context,
        [
            auth_context(roles_config),
            schema_validate(),
            evidence_validate(),
            classify_write_route(),
            review_route(),
            persist(),
            audit_append(),
        ],
    )

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "audit_path"
    assert not (context["kb_root"] / "staging" / "KB-2026-0001.md").exists()


def test_audit_failure_logs_when_rollback_unlink_fails(
    make_context: Callable[..., MiddlewareContext],
    roles_config: RolesConfig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_append(*args: object, **kwargs: object) -> None:
        raise PermissionError("audit blocked")

    def fail_unlink(self: Path) -> None:
        raise OSError("file locked")

    monkeypatch.setattr("governed_api.middleware.append_audit_record", fail_append)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    caplog.set_level(logging.ERROR, logger="governed_api.middleware")
    context = make_context(payload=entry_payload(entry_id=None, trust_state="pending"))

    result = run_pipeline(
        context,
        [
            auth_context(roles_config),
            schema_validate(),
            evidence_validate(),
            classify_write_route(),
            review_route(),
            persist(),
            audit_append(),
        ],
    )

    orphan_path = context["kb_root"] / "staging" / "KB-2026-0001.md"
    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "audit_path"
    assert orphan_path.exists()
    assert "回滚失败" in caplog.text
    assert str(orphan_path) in caplog.text
    assert "file locked" in caplog.text


def test_validation_failure_prevents_persist_and_audit(
    make_context: Callable[..., MiddlewareContext],
    roles_config: RolesConfig,
) -> None:
    context = make_context(payload=entry_payload(entry_id=None, evidence=[{"type": "human_note"}]))
    result = run_pipeline(
        context,
        [
            auth_context(roles_config),
            schema_validate(),
            evidence_validate(),
            classify_write_route(),
            review_route(),
            persist(),
            audit_append(),
        ],
    )

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_SCHEMA"
    assert not (context["kb_root"] / "staging").exists()
    assert not (context["kb_root"] / "indexes" / "audit.jsonl").exists()
