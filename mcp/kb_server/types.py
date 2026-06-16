"""Typed dictionaries for Phase 3 MCP tool payloads."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from index.types import SearchResult as SearchResult
from index.types import SearchScope as SearchScope

__all__ = [
    "ProposeResult",
    "SearchResult",
    "SearchScope",
    "ToolCallResult",
    "ToolDescriptor",
]


class ProposeResult(TypedDict, total=False):
    proposed_id: str
    id: str
    status: Literal["pending", "auto_published"]
    validation_errors: list[dict[str, Any]]
    validation_warnings: list[dict[str, Any]]
    missing_fields: list[str]
    open_questions: list[str]
    possible_duplicates: list[str]
    review_level: str


class ToolDescriptor(TypedDict):
    name: str
    description: str
    inputSchema: dict[str, Any]


class ToolCallResult(TypedDict):
    content: list[dict[str, str]]
    isError: NotRequired[bool]
