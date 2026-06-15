from __future__ import annotations

from pathlib import Path

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


def test_pipeline_catches_exceptions_and_rolls_back_unaudited_write(tmp_path: Path) -> None:
    persisted_path = tmp_path / "kb" / "staging" / "KB-2026-0001.md"
    persisted_path.parent.mkdir(parents=True)
    persisted_path.write_text("entry", encoding="utf-8")
    context: MiddlewareContext = {
        "auth": {"user": "alice", "role": "contributor"},
        "operation": "create",
        "payload": {},
        "persisted_path": persisted_path,
    }

    def boom(current: MiddlewareContext) -> MiddlewareResult:
        raise RuntimeError("audit writer exploded")

    result = run_pipeline(context, [boom])

    assert not result["ok"]
    assert result["error"] is not None
    assert result["error"].field == "middleware"
    assert not persisted_path.exists()
