"""Governed API middleware pipeline for unified-kb."""

from governed_api.middleware import (
    audit_append,
    auth_context,
    classify_write_route,
    evidence_validate,
    persist,
    review_route,
    schema_validate,
)
from governed_api.pipeline import run_pipeline
from governed_api.roles import RolesConfig, load_roles_config, require_permission
from governed_api.types import ApiError, MiddlewareContext, MiddlewareResult

__all__ = [
    "ApiError",
    "MiddlewareContext",
    "MiddlewareResult",
    "RolesConfig",
    "audit_append",
    "auth_context",
    "classify_write_route",
    "evidence_validate",
    "load_roles_config",
    "persist",
    "require_permission",
    "review_route",
    "run_pipeline",
    "schema_validate",
]
