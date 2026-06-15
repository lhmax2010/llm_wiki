from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from governed_api.roles import RolesConfig
from governed_api.types import MiddlewareContext

from core.id_allocator import IDAllocator
from tests.governed_api.helpers import entry_payload


@pytest.fixture
def roles_config() -> RolesConfig:
    return RolesConfig(
        roles={
            "reader": ["read_published"],
            "contributor": ["read_published", "propose_entry"],
            "reviewer": ["read_published", "propose_entry", "review_light", "review_heavy"],
            "admin": ["*"],
        },
        users={"alice": "contributor", "reviewer": "reviewer"},
    )


@pytest.fixture
def make_context(tmp_path: Path) -> Callable[..., MiddlewareContext]:
    def _make_context(
        *,
        payload: dict[str, Any] | None = None,
        operation: str = "create",
        role: str = "contributor",
        user: str = "alice",
        include_roots: bool = True,
    ) -> MiddlewareContext:
        context: MiddlewareContext = {
            "auth": {"user": user, "role": role},
            "operation": operation,
            "payload": payload or entry_payload(),
        }
        if include_roots:
            kb_root = tmp_path / "kb"
            context["repo_root"] = tmp_path
            context["kb_root"] = kb_root
            context["id_allocator"] = IDAllocator(kb_root / "indexes" / "ids.sqlite")
        return context

    return _make_context
