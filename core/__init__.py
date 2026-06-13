"""Content-core primitives for the unified knowledge base."""

from core.errors import IssueCode, ValidationIssue
from core.id_allocator import IDAllocator
from core.models import Entry
from core.validation import ValidationReport, validate_entry

__all__ = [
    "Entry",
    "IDAllocator",
    "IssueCode",
    "ValidationIssue",
    "ValidationReport",
    "validate_entry",
]
