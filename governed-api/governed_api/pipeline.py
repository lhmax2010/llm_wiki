"""Sequential middleware runner."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from governed_api.types import ApiError, Middleware, MiddlewareContext, MiddlewareResult, fail, ok

LOGGER = logging.getLogger(__name__)


def run_pipeline(context: MiddlewareContext, middleware: Iterable[Middleware]) -> MiddlewareResult:
    current = context
    for step in middleware:
        try:
            result = step(current)
        except Exception as exc:
            _rollback_persisted_path(current)
            return fail(
                current,
                ApiError(
                    "E_SCHEMA",
                    f"middleware raised {type(exc).__name__}: {exc}",
                    "middleware",
                ),
            )
        if not result["ok"]:
            return result
        current = result["context"]
    return ok(current)


def _rollback_persisted_path(context: MiddlewareContext) -> None:
    path = context.get("persisted_path")
    if path is not None and path.exists() and "audit_record" not in context:
        try:
            path.unlink()
        except OSError as exc:
            LOGGER.error("回滚失败: %s (%s) - orphaned unaudited entry", path, exc)
