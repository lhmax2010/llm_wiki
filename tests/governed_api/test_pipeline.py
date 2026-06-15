from __future__ import annotations

from governed_api.pipeline import run_pipeline
from governed_api.types import ApiError, MiddlewareContext, MiddlewareResult, fail, ok


def test_pipeline_stops_on_first_failure() -> None:
    calls: list[str] = []
    context: MiddlewareContext = {
        "auth": {"user": "alice", "role": "contributor"},
        "operation": "create",
        "payload": {},
    }

    def first(current: MiddlewareContext) -> MiddlewareResult:
        calls.append("first")
        return fail(current, ApiError("E_TEST", "stop here"))

    def second(current: MiddlewareContext) -> MiddlewareResult:
        calls.append("second")
        return ok(current)

    result = run_pipeline(context, [first, second])

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].code == "E_TEST"
    assert calls == ["first"]
