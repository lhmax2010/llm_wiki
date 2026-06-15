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
            "reviewer": [
                "read_published",
                "create_research",
                "edit_own_research",
                "propose_entry",
                "promote_research_to_draft",
                "review_light",
                "review_heavy",
            ],
            "admin": ["*"],
        },
        users={"alice": "contributor", "reader": "reader", "reviewer": "reviewer"},
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
        if payload is None:
            payload = entry_payload(
                entry_id=None
                if operation in {"create", "propose", "propose_entry"}
                else "KB-2026-0001"
            )
        context: MiddlewareContext = {
            "auth": {"user": user, "role": role},
            "operation": operation,
            "payload": payload,
        }
        if include_roots:
            kb_root = tmp_path / "kb"
            context["repo_root"] = tmp_path
            context["kb_root"] = kb_root
            context["id_allocator"] = IDAllocator(kb_root / "indexes" / "ids.sqlite")
        return context

    return _make_context
