"""Read-only service layer for the Phase 7a Web API."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from core.models import Entry
from index import IndexUnavailable, SearchService
from index.sqlite_index import read_valid_entries_from_source, read_valid_entry_file
from index.types import SearchResult, SearchScope

LOGGER = logging.getLogger(__name__)

KB_ID_RE = re.compile(r"^KB-\d{4}-\d{4}$")
PUBLISHED_DIR = "entries"
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
SortParam = Literal["score", "updated_desc", "title"]


@dataclass(frozen=True, slots=True)
class WebApiError(Exception):
    code: str
    message: str
    field: str | None = None
    status_code: int = 400


@dataclass(frozen=True, slots=True)
class WebReadService:
    """Human read facade backed by P4 safe search and entry readers."""

    kb_root: Path
    search_service: SearchService | None = None

    def search_entries(
        self,
        query: str,
        *,
        scope: SearchScope | None = None,
        expand_synonyms: bool = True,
        limit: int = 20,
        offset: int = 0,
        sort: SortParam = "score",
    ) -> list[SearchResult]:
        service = self.search_service or SearchService(self.kb_root)
        try:
            return service.search_human(
                query,
                scope=scope,
                expand_synonyms=expand_synonyms,
                limit=limit,
                offset=offset,
                sort=sort,
            )
        except IndexUnavailable as exc:
            LOGGER.warning("human search index unavailable, using entries-only fallback: %s", exc)
        return service.search_human_direct(
            query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        path = _published_entry_path(self.kb_root, entry_id)
        if not path.is_file():
            raise WebApiError("E_SCHEMA", f"entry not found: {entry_id}", "id", 404)
        try:
            item = read_valid_entry_file(
                self.kb_root,
                PUBLISHED_DIR,
                path,
                context="web api get_entry",
            )
        except ValueError as exc:
            LOGGER.warning("web api get_entry invalid entry source for %s: %s", entry_id, exc)
            raise WebApiError("E_SCHEMA", "invalid entry source", "id") from exc
        if item is None:
            raise WebApiError("E_SCHEMA", f"entry is unreadable or invalid: {entry_id}", "id", 404)
        return item.entry.model_dump(mode="json")

    def list_categories(self) -> dict[str, list[str]]:
        entries = self._published_entries()
        return {
            "modules": sorted({entry.module for entry in entries}),
            "entry_types": sorted({entry.entry_type.value for entry in entries}),
            "tags": sorted({tag for entry in entries for tag in entry.tags}),
            "error_codes": sorted({code for entry in entries for code in entry.error_codes}),
        }

    def browse(
        self,
        *,
        module: str,
        entry_type: EntryTypeParam | None = None,
    ) -> dict[str, Any]:
        entries = [
            entry
            for entry in self._published_entries()
            if entry.module == module
            and (entry_type is None or entry.entry_type.value == entry_type)
        ]
        return {
            "module": module,
            "entry_type": entry_type,
            "entries": [
                _entry_summary(entry) for entry in sorted(entries, key=lambda item: item.id)
            ],
        }

    def _published_entries(self) -> list[Entry]:
        try:
            indexed, _ = read_valid_entries_from_source(
                self.kb_root,
                PUBLISHED_DIR,
                context="web api published scan",
            )
        except ValueError as exc:
            LOGGER.warning("web api published scan invalid source: %s", exc)
            raise WebApiError("E_SCHEMA", "invalid published source", "kb_root") from exc
        return [item.entry for item in indexed]


def build_scope(
    *,
    module: str | None = None,
    entry_type: EntryTypeParam | None = None,
    error_code: str | None = None,
    claim_type: ClaimTypeParam | None = None,
    min_support: SupportParam | None = None,
    exclude_stale: bool = False,
    status: Literal["published"] | None = None,
) -> SearchScope:
    scope: SearchScope = {}
    if module:
        scope["module"] = module
    if entry_type:
        scope["entry_type"] = entry_type
    if error_code:
        scope["error_code"] = error_code
    if claim_type:
        scope["claim_type"] = claim_type
    if min_support:
        scope["min_support"] = min_support
    if exclude_stale:
        scope["exclude_stale"] = True
    if status:
        scope["status"] = status
    return scope


def _published_entry_path(kb_root: Path, entry_id: str) -> Path:
    if not KB_ID_RE.fullmatch(entry_id):
        raise WebApiError("E_SCHEMA", "id must match KB-{year}-{NNNN}", "id")
    base = _published_root(kb_root)
    path = (base / f"{entry_id}.md").resolve()
    if not path.is_relative_to(base):
        raise WebApiError("E_SCHEMA", "entry path escaped published directory", "id")
    return path


def _published_root(kb_root: Path) -> Path:
    root = kb_root.resolve()
    source_path = root / PUBLISHED_DIR
    if source_path.exists() and source_path.is_symlink():
        raise WebApiError("E_SCHEMA", "entries directory must not be a symlink", "kb_root")
    resolved = source_path.resolve()
    if not resolved.is_relative_to(root):
        raise WebApiError("E_SCHEMA", "entries directory escapes kb root", "kb_root")
    return resolved


def _entry_summary(entry: Entry) -> dict[str, Any]:
    stale = bool(entry.code_binding.stale) if entry.code_binding is not None else False
    return {
        "id": entry.id,
        "title": entry.title,
        "entry_type": entry.entry_type.value,
        "module": entry.module,
        "trust_state": entry.trust_state.value,
        "claim_type": entry.credibility.claim_type.value,
        "support_strength": entry.credibility.support_strength.value,
        "stale": stale,
    }
