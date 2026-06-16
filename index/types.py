"""Shared search types for the index layer and MCP wrapper."""

from __future__ import annotations

from typing import Any, Required, TypedDict


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


class ResearchSignal(TypedDict, total=False):
    id: Required[str]
    title: Required[str]
    snippet: Required[str]
    trust_state: Required[str]
    warning: Required[str]
    tags: list[str]
    created: str
    expires_at: str | None
    score: int
