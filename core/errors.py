"""Validation issue types shared by content-core modules."""

from dataclasses import dataclass
from enum import StrEnum


class IssueCode(StrEnum):
    """Design-defined validation and warning codes."""

    E_SCHEMA = "E_SCHEMA"
    E_EVIDENCE_MISSING = "E_EVIDENCE_MISSING"
    E_EVIDENCE_NOT_FOUND = "E_EVIDENCE_NOT_FOUND"
    E_DUP = "E_DUP"
    E_PERM = "E_PERM"
    E_RESEARCH_AS_EVIDENCE = "E_RESEARCH_AS_EVIDENCE"
    W_DOWNGRADE = "W_DOWNGRADE"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A design §4.3/§4.4 compatible validation issue."""

    code: IssueCode
    field: str
    message: str
