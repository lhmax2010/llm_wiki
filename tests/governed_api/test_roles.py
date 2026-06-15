from __future__ import annotations

from pathlib import Path

from governed_api.roles import load_roles_config, permission_error, require_permission
from governed_api.types import MiddlewareContext, MiddlewareResult, ok


def test_load_roles_config_and_admin_wildcard(tmp_path: Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(
        """
roles:
  contributor: [read_published, propose_entry]
  reviewer: [read_published, propose_entry, create_research]
  admin: ["*"]
users:
  alice: contributor
  bob: reviewer
""",
        encoding="utf-8",
    )

    config = load_roles_config(path)

    assert config.role_for_user("alice") == "contributor"
    assert config.has_permission("contributor", "propose_entry")
    assert config.has_permission("reviewer", "propose_entry")
    assert config.has_permission("reviewer", "create_research")
    assert config.has_permission("admin", "delete_the_moon")


def test_project_roles_yaml_expands_reviewer_permissions() -> None:
    config = load_roles_config(Path("config/roles.yaml"))

    assert config.has_permission("reviewer", "propose_entry")
    assert config.has_permission("reviewer", "create_research")
    assert config.has_permission("reviewer", "promote_research_to_draft")


def test_require_permission_decorator_blocks_missing_permission() -> None:
    @require_permission("publish_entry")
    def handler(context: MiddlewareContext) -> MiddlewareResult:
        return ok(context)

    context: MiddlewareContext = {
        "auth": {"user": "alice", "role": "contributor", "permissions": ["propose_entry"]},
        "operation": "create",
        "payload": {},
    }

    result = handler(context)

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_PERM"
    assert permission_error(context, "propose_entry") is None
