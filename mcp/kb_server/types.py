"""Typed dictionaries for Phase 3 MCP tool payloads."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, Required, TypedDict


class SearchScope(TypedDict, total=False):
    module: str
    entry_type: str
    error_code: str
    claim_type: str
    min_support: str
    exclude_stale: bool
    status: str


class SearchResult(TypedDict, total=False):
    id: Required[str]
    title: Required[str]
    entry_type: Required[str]
    module: Required[str]
    snippet: Required[str]
    matched_section: str | None
    credibility: Required[dict[str, Any]]
    trust_state: Required[str]
    stale: bool
    score: int


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
