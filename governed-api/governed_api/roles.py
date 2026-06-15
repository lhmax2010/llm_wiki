"""YAML-backed V1 RBAC helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml  # type: ignore[import-untyped]

from governed_api.types import ApiError, MiddlewareContext, MiddlewareResult, fail

ADMIN_PERMISSION = "*"


class PermissionDeniedError(Exception):
    """Raised by imperative permission checks."""


@dataclass(frozen=True, slots=True)
class RolesConfig:
    roles: dict[str, list[str]]
    users: dict[str, str]

    def permissions_for_role(self, role: str) -> list[str]:
        if role not in self.roles:
            raise KeyError(f"unknown role: {role}")
        return list(self.roles[role])

    def role_for_user(self, user: str) -> str | None:
        return self.users.get(user)

    def has_permission(self, role: str, permission: str) -> bool:
        permissions = self.permissions_for_role(role)
        return ADMIN_PERMISSION in permissions or permission in permissions

    def permissions_for_user(self, user: str) -> tuple[str, list[str]]:
        role = self.role_for_user(user)
        if role is None:
            raise KeyError(f"unknown user: {user}")
        return role, self.permissions_for_role(role)


def load_roles_config(path: Path) -> RolesConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("roles config must be a YAML mapping")
    raw_roles = data.get("roles", {})
    raw_users = data.get("users", {})
    if not isinstance(raw_roles, dict):
        raise ValueError("roles config 'roles' must be a mapping")
    if not isinstance(raw_users, dict):
        raise ValueError("roles config 'users' must be a mapping")

    roles: dict[str, list[str]] = {}
    for role, permissions in raw_roles.items():
        if not isinstance(role, str) or not isinstance(permissions, list):
            raise ValueError("roles config permissions must be lists keyed by role name")
        if not all(isinstance(permission, str) for permission in permissions):
            raise ValueError("roles config permissions must be strings")
        roles[role] = list(permissions)

    users: dict[str, str] = {}
    for user, role in raw_users.items():
        if not isinstance(user, str) or not isinstance(role, str):
            raise ValueError("roles config users must map strings to role names")
        users[user] = role

    return RolesConfig(roles=roles, users=users)


def permission_error(context: MiddlewareContext, permission: str) -> ApiError | None:
    auth = context.get("auth", {})
    permissions = auth.get("permissions", [])
    if ADMIN_PERMISSION in permissions or permission in permissions:
        return None
    return ApiError(
        code="E_PERM",
        field="auth.permissions",
        message=f"permission required: {permission}",
    )


Handler = TypeVar("Handler", bound=Callable[..., MiddlewareResult])


def require_permission(permission: str) -> Callable[[Handler], Handler]:
    """Decorate a handler that accepts MiddlewareContext as its first argument."""

    def decorator(handler: Handler) -> Handler:
        @wraps(handler)
        def wrapper(context: MiddlewareContext, *args: Any, **kwargs: Any) -> MiddlewareResult:
            error = permission_error(context, permission)
            if error is not None:
                return fail(context, error)
            return handler(context, *args, **kwargs)

        return cast(Handler, wrapper)

    return decorator
