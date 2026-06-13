"""Pydantic models for design §4.4 content-core schema."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceType(StrEnum):
    CODE = "code"
    LOG = "log"
    REPRO = "repro"
    SPEC = "spec"
    TICKET = "ticket"
    HISTORICAL_ENTRY = "historical_entry"
    HUMAN_NOTE = "human_note"
    ATTACHMENT = "attachment"


class ClaimType(StrEnum):
    FACT = "fact"
    OBSERVATION = "observation"
    STATIC_INFERENCE = "static_inference"
    HISTORICAL_PATTERN = "historical_pattern"
    LLM_HYPOTHESIS = "llm_hypothesis"
    SPEC = "spec"


class SupportStrength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class EdgeType(StrEnum):
    SIMILAR_SYMPTOM = "similar_symptom"
    SAME_ROOT_CAUSE = "same_root_cause"
    SUPERSEDES = "supersedes"
    DUPLICATES = "duplicates"
    EVIDENCE_FOR = "evidence_for"
    RELATED = "related"


class EdgeOrigin(StrEnum):
    HUMAN = "human"
    RULE = "rule"
    LLM_SUGGESTED = "llm_suggested"


class SymbolResolution(StrEnum):
    CLANGD = "clangd"
    TREE_SITTER = "tree_sitter"
    FALLBACK_PATH = "fallback_path"


class EntryType(StrEnum):
    DEFECT_CASE = "defect_case"
    TRIAGE_RULE = "triage_rule"
    CODE_FLOW = "code_flow"
    LOG_BASELINE = "log_baseline"


class TrustState(StrEnum):
    RESEARCH = "research"
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class AuthorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class StrictModel(BaseModel):
    """Base model matching the frozen schema: no undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    """Evidence union. Type-specific required fields are enforced by validators."""

    type: EvidenceType
    filepath: str | None = None
    line: int | None = None
    symbol: str | None = None
    sha: str | None = None
    attachment_id: str | None = None
    line_range: str | None = None
    excerpt: str | None = None
    uri: str | None = None
    version: str | None = None
    section: str | None = None
    ref: str | None = None


class Credibility(StrictModel):
    claim_type: ClaimType
    support_strength: SupportStrength
    evidence: list[Evidence] = Field(default_factory=list)


class SectionCredibility(StrictModel):
    claim_type: ClaimType | None = None
    support_strength: SupportStrength | None = None
    evidence: list[Evidence] | None = None


class RelatedEdge(StrictModel):
    target: str | None = None
    type: EdgeType | None = None
    origin: EdgeOrigin | None = None
    note: str | None = None


class CodeBinding(StrictModel):
    repo_id: str | None = None
    git_sha: str | None = None
    paths: list[str] = Field(default_factory=list)
    path_hashes: dict[str, str] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    symbol_hashes: dict[str, str] = Field(default_factory=dict)
    symbol_resolution: SymbolResolution | None = None
    build_config_id: str | None = None
    build_config_hash: str | None = None
    stale: bool | None = None
    stale_reason: str | None = None


class Entry(StrictModel):
    id: str
    schema_version: int
    entry_type: EntryType
    title: str
    module: str
    credibility: Credibility
    trust_state: TrustState
    author_type: AuthorType
    created: str
    updated: str
    body: str
    tags: list[str] = Field(default_factory=list)
    symptom_keywords: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    log_signatures: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    versions_affected: list[str] = Field(default_factory=list)
    hardware: list[str] = Field(default_factory=list)
    severity: str | None = None
    section_credibility: dict[str, SectionCredibility] = Field(default_factory=dict)
    code_binding: CodeBinding | None = None
    related: list[RelatedEdge] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    trigger: str | None = None
    author: str | None = None
    reviewer: str | None = None
    inferred_fields: list[str] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def require_schema_v3(cls, value: int) -> int:
        if value != 3:
            raise ValueError("schema_version must be 3")
        return value


class EntryUpdate(StrictModel):
    title: str | None = None
    module: str | None = None
    tags: list[str] | None = None
    symptom_keywords: list[str] | None = None
    error_codes: list[str] | None = None
    aliases: list[str] | None = None
    severity: str | None = None
    credibility: Credibility | None = None
    section_credibility: dict[str, SectionCredibility] | None = None
    code_binding: CodeBinding | None = None
    related: list[RelatedEdge] | None = None
    body: str | None = None
