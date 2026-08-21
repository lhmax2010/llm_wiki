"""Declared, enforced argument schemas for the MCP tools.

These models are the single source of truth for two things that must never
drift apart: what ``tools/list`` advertises to an agent, and what the server
accepts on ``tools/call``. The JSON Schema handed to the agent is generated
from the same model that validates the call, so a field cannot be documented
without being enforced, or enforced without being documented.

Why this exists: the tools previously advertised
``{"type": "object", "additionalProperties": true}`` -- zero declared
properties -- and the server passed ``**arguments`` straight through. An agent
could neither discover that ``search_kb`` takes a ``scope``, nor find out that
it had misspelled one. ``scope={"modules": "photo"}`` was silently ignored and
the search returned the whole KB, which an agent doing duplicate-detection
would read as "this module already has many similar entries".

Strictness boundary: tool arguments and ``scope`` are strict (``extra=forbid``)
because their key set is closed and a typo there silently changes the result
set. ``draft`` / ``patch`` / ``credibility`` stay open ``dict[str, Any]``:
those are entry payloads whose shape belongs to the Governed API pipeline,
which validates them properly downstream. Locking them here would duplicate
that contract and break proposals the pipeline would have accepted.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EntryTypeParam = Literal["defect_case", "triage_rule", "code_flow", "log_baseline"]
ClaimTypeParam = Literal[
    "fact",
    "observation",
    "static_inference",
    "historical_pattern",
    "llm_hypothesis",
    "spec",
]
SupportParam = Literal["weak", "moderate", "strong"]
TrustStateParam = Literal["research", "draft", "pending", "published", "deprecated"]
SortParam = Literal["score", "updated_desc", "title"]

QUERY_MAX_LENGTH = 200
SHORT_TEXT_MAX_LENGTH = 120
LIMIT_MAX = 100


class ToolArgs(BaseModel):
    """Base for tool arguments: unknown keys are an error, not a shrug."""

    model_config = ConfigDict(extra="forbid")

    def to_kwargs(self) -> dict[str, Any]:
        """Handler kwargs. Unset optionals are dropped so handler defaults win."""
        return self.model_dump(exclude_none=True)


class SearchScopeArgs(ToolArgs):
    """Filters applied to every candidate entry.

    Every field is optional and omitting one means "do not filter on it".
    A misspelled key is rejected rather than ignored -- silently searching a
    wider set than the caller asked for is the failure mode this guards.
    """

    module: str | None = Field(
        default=None,
        max_length=SHORT_TEXT_MAX_LENGTH,
        description="Restrict to one module, e.g. 'photo'. Exact match.",
    )
    entry_type: EntryTypeParam | None = Field(
        default=None,
        description="Restrict to one entry type.",
    )
    error_code: str | None = Field(
        default=None,
        max_length=SHORT_TEXT_MAX_LENGTH,
        description="Restrict to entries listing this error code.",
    )
    claim_type: ClaimTypeParam | None = Field(
        default=None,
        description="Restrict to one credibility claim type.",
    )
    min_support: SupportParam | None = Field(
        default=None,
        description=(
            "Minimum supporting strength. An entry whose own support is lower "
            "still matches if one of its sections meets the bar; that section "
            "is reported back as matched_section."
        ),
    )
    exclude_stale: bool | None = Field(
        default=None,
        description="Drop entries whose code binding is marked stale.",
    )
    status: TrustStateParam | None = Field(
        default=None,
        description="Restrict to one trust state.",
    )


class SearchKbArgs(ToolArgs):
    query: str = Field(
        max_length=QUERY_MAX_LENGTH,
        description="Free text. Matched against id, title, summary, module, body, tags, "
        "aliases, symptom keywords, error codes and log signatures.",
    )
    scope: SearchScopeArgs | None = Field(
        default=None,
        description="Optional filters. Omit to search all published entries.",
    )
    include_pending: bool = Field(
        default=False,
        description="Also search staging proposals awaiting review.",
    )
    expand_synonyms: bool = Field(
        default=True,
        description="Expand the query through kb/synonyms.jsonl when it exactly "
        "matches a canonical term or one of its synonyms.",
    )
    limit: int = Field(default=20, ge=0, le=LIMIT_MAX)
    offset: int = Field(default=0, ge=0)
    sort: SortParam = Field(default="score")


class GetEntryArgs(ToolArgs):
    id: str = Field(
        max_length=64,
        description="Entry id, e.g. 'KB-2026-0001'.",
    )
    include_pending: bool = Field(
        default=False,
        description="Also look in staging for a proposal with this id.",
    )


class ListCategoriesArgs(ToolArgs):
    """Takes no arguments."""


class BrowseArgs(ToolArgs):
    module: str = Field(
        max_length=SHORT_TEXT_MAX_LENGTH,
        description="Module to list entries for. Exact match.",
    )
    entry_type: EntryTypeParam | None = Field(
        default=None,
        description="Optionally narrow to one entry type.",
    )


class ProposeEntryArgs(ToolArgs):
    draft: dict[str, Any] = Field(
        description="Entry fields (title, summary, module, entry_type, body, tags, ...). "
        "Validated by the Governed API pipeline, not here.",
    )
    credibility: dict[str, Any] = Field(
        description="claim_type, support_strength and evidence for the new entry.",
    )
    request_id: str = Field(max_length=128, description="Caller-supplied idempotency key.")


class ProposeUpdateArgs(ToolArgs):
    id: str = Field(max_length=64, description="Entry id to update.")
    patch: dict[str, Any] = Field(
        description="Fields to change. May carry change_scopes / changed_fields to declare "
        "the intent of the edit.",
    )
    reason: str = Field(max_length=500, description="Why this update is proposed.")
    credibility: dict[str, Any] | None = Field(
        default=None,
        description="Only send this when deliberately changing the trust verdict. "
        "Omit it and the published credibility is preserved.",
    )
    request_id: str | None = Field(default=None, max_length=128)


class SearchResearchForHintsArgs(ToolArgs):
    query: str = Field(max_length=QUERY_MAX_LENGTH)


TOOL_ARGS: dict[str, type[ToolArgs]] = {
    "search_kb": SearchKbArgs,
    "get_entry": GetEntryArgs,
    "list_categories": ListCategoriesArgs,
    "browse": BrowseArgs,
    "propose_entry": ProposeEntryArgs,
    "propose_update": ProposeUpdateArgs,
    "search_research_for_hints": SearchResearchForHintsArgs,
}


def input_schema_for(model: type[ToolArgs]) -> dict[str, Any]:
    """JSON Schema for a tool, with nested definitions inlined.

    Pydantic emits nested models as ``$ref`` into ``$defs``. That is valid JSON
    Schema, but MCP clients vary in whether they resolve it, and a client that
    does not would show the agent an opaque ``scope`` object -- reintroducing
    exactly the discovery problem this module exists to fix. Inlining keeps the
    schema self-contained.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    inlined = _inline_refs(schema, definitions)
    assert isinstance(inlined, dict)  # a dict in is always a dict out
    return inlined


def _inline_refs(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = definitions.get(ref.removeprefix("#/$defs/"), {})
            merged = {**_inline_refs(target, definitions)}
            # Keep sibling keys such as an overriding description.
            for key, value in node.items():
                if key != "$ref":
                    merged[key] = _inline_refs(value, definitions)
            return merged
        return {key: _inline_refs(value, definitions) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline_refs(item, definitions) for item in node]
    return node
