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
  admin: ["*"]
users:
  alice: contributor
""",
        encoding="utf-8",
    )

    config = load_roles_config(path)

    assert config.role_for_user("alice") == "contributor"
    assert config.has_permission("contributor", "propose_entry")
    assert config.has_permission("admin", "delete_the_moon")


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
