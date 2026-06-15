from __future__ import annotations

from typing import Any

from core.models import Entry
from core.validation import headings_for_entry_type


def body_for(entry_type: str = "defect_case") -> str:
    headings = headings_for_entry_type(entry_type)  # type: ignore[arg-type]
    return "\n\n".join(f"## {heading}\n{heading} content." for heading in headings)


def entry_payload(
    *,
    entry_id: str | None = "KB-2026-0001",
    trust_state: str = "pending",
    claim_type: str = "observation",
    evidence: list[dict[str, object]] | None = None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 3,
        "entry_type": "defect_case",
        "title": "Decoder failure",
        "module": "decoder",
        "credibility": {
            "claim_type": claim_type,
            "support_strength": "strong",
            "evidence": evidence
            if evidence is not None
            else [{"type": "human_note", "excerpt": "Observed by reviewer."}],
        },
        "trust_state": trust_state,
        "author_type": "human",
        "created": "2026-06-15T00:00:00Z",
        "updated": "2026-06-15T00:00:00Z",
        "body": body_for(),
        "aliases": aliases or [],
    }
    if entry_id is not None:
        payload["id"] = entry_id
    return payload


def entry_from_payload(payload: dict[str, Any]) -> Entry:
    return Entry.model_validate(payload)
