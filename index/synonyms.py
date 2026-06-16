"""Synonym loading and query expansion for Phase 4 search."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SynonymGroup:
    canonical: str
    synonyms: tuple[str, ...]

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.canonical, *self.synonyms)


def load_synonym_groups(path: Path) -> list[SynonymGroup]:
    if not path.is_file():
        return []
    groups: list[SynonymGroup] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        groups.append(_group_from_payload(payload, path=path, line_number=line_number))
    return groups


def expand_query_terms(query: str, groups: list[SynonymGroup], *, enabled: bool) -> list[str]:
    normalized_query = query.strip()
    if not normalized_query:
        return [""]
    terms = [normalized_query]
    if not enabled:
        return terms

    query_lower = normalized_query.lower()
    for group in groups:
        lower_terms = {term.lower() for term in group.terms}
        if query_lower in lower_terms:
            terms.extend(group.terms)

    seen: set[str] = set()
    expanded: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            expanded.append(term)
            seen.add(key)
    return expanded


def _group_from_payload(payload: Any, *, path: Path, line_number: int) -> SynonymGroup:
    if not isinstance(payload, dict):
        raise ValueError(f"synonym line must be an object: {path}:{line_number}")
    canonical = payload.get("canonical")
    synonyms = payload.get("synonyms")
    if not isinstance(canonical, str) or not canonical.strip():
        raise ValueError(f"synonym canonical must be a non-empty string: {path}:{line_number}")
    if not isinstance(synonyms, list) or not all(isinstance(item, str) for item in synonyms):
        raise ValueError(f"synonyms must be a string list: {path}:{line_number}")
    return SynonymGroup(
        canonical=canonical.strip(),
        synonyms=tuple(item.strip() for item in synonyms if item.strip()),
    )
