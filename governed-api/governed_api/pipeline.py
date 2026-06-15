"""Sequential middleware runner."""

from __future__ import annotations

from collections.abc import Iterable

from governed_api.types import Middleware, MiddlewareContext, MiddlewareResult, ok


def run_pipeline(context: MiddlewareContext, middleware: Iterable[Middleware]) -> MiddlewareResult:
    current = context
    for step in middleware:
        result = step(current)
        if not result["ok"]:
            return result
        current = result["context"]
    return ok(current)
