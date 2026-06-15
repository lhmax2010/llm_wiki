from __future__ import annotations

from collections.abc import Iterable

import pytest

from core.models import Entry
from core.validation import headings_for_entry_type


def body_for(entry_type: str) -> str:
    headings = headings_for_entry_type(entry_type)  # type: ignore[arg-type]
    return "\n\n".join(f"## {heading}\n{heading} content." for heading in headings)


def code_binding() -> dict[str, object]:
    return {
        "repo_id": "main",
        "git_sha": "a" * 40,
        "paths": ["src/decoder.c"],
        "path_hashes": {"src/decoder.c": "b" * 64},
        "symbols": ["decode_hdr_frame"],
        "symbol_hashes": {"decode_hdr_frame": "c" * 64},
        "symbol_resolution": "fallback_path",
        "build_config_id": "default",
        "build_config_hash": "d" * 16,
        "stale": False,
        "stale_reason": None,
    }


@pytest.fixture
def make_entry() -> object:
    def _make_entry(
        *,
        entry_type: str = "defect_case",
        trust_state: str = "published",
        claim_type: str = "observation",
        evidence: Iterable[dict[str, object]] | None = None,
        include_code_binding: bool | None = None,
        body: str | None = None,
        section_credibility: dict[str, object] | None = None,
    ) -> Entry:
        needs_binding = entry_type in {"code_flow", "log_baseline"}
        payload = {
            "id": "KB-2026-0001",
            "schema_version": 3,
            "entry_type": entry_type,
            "title": "Decoder failure",
            "module": "decoder",
            "credibility": {
                "claim_type": claim_type,
                "support_strength": "strong",
                "evidence": list(
                    evidence
                    if evidence is not None
                    else [{"type": "human_note", "excerpt": "Observed by reviewer."}]
                ),
            },
            "trust_state": trust_state,
            "author_type": "human",
            "created": "2026-06-13T00:00:00Z",
            "updated": "2026-06-13T00:00:00Z",
            "body": body if body is not None else body_for(entry_type),
            "section_credibility": section_credibility or {},
        }
        if include_code_binding if include_code_binding is not None else needs_binding:
            payload["code_binding"] = code_binding()
        return Entry.model_validate(payload)

    return _make_entry
