"""Search service built on the Phase 4 metadata indexes."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from core.models import Entry
from core.storage import read_entry
from index.cjk import cjk_bigram_match, contains_cjk
from index.sqlite_index import IndexBuildResult, SQLiteMetadataIndex
from index.synonyms import expand_query_terms, load_synonym_groups
from index.types import SearchResult, SearchScope

LOGGER = logging.getLogger(__name__)
SUPPORT_RANK = {"weak": 0, "moderate": 1, "strong": 2}
PUBLISHED_DIR = "entries"
PENDING_DIR = "staging"


@dataclass(frozen=True, slots=True)
class ResearchSearchIndex:
    """P4 placeholder for P6 research search.

    The class intentionally shares the query shape with real indexes but does not
    scan or index kb/research. P6 can replace this implementation behind the same
    interface once research isolation is implemented.
    """

    name: str = "research_search_index"

    def rebuild(self, kb_root: Path) -> IndexBuildResult:
        del kb_root
        return IndexBuildResult(
            index_name=self.name,
            indexed_entries=0,
            skipped_files=0,
            status="placeholder",
        )

    def search(self, query: str) -> list[SearchResult]:
        del query
        return []


@dataclass(frozen=True, slots=True)
class SearchService:
    kb_root: Path

    @property
    def agent_index(self) -> SQLiteMetadataIndex:
        return SQLiteMetadataIndex(
            name="agent_search_index",
            db_path=self.kb_root / "indexes" / "agent_search_index" / "metadata.sqlite",
            source_dirs=(PUBLISHED_DIR,),
        )

    @property
    def human_index(self) -> SQLiteMetadataIndex:
        return SQLiteMetadataIndex(
            name="human_search_index",
            db_path=self.kb_root / "indexes" / "human_search_index" / "metadata.sqlite",
            source_dirs=(PUBLISHED_DIR,),
        )

    @property
    def research_index(self) -> ResearchSearchIndex:
        return ResearchSearchIndex()

    def rebuild_agent_index(self) -> IndexBuildResult:
        return self.agent_index.rebuild(self.kb_root)

    def rebuild_human_index(self) -> IndexBuildResult:
        return self.human_index.rebuild(self.kb_root)

    def rebuild_research_index(self) -> IndexBuildResult:
        return self.research_index.rebuild(self.kb_root)

    def search_agent(
        self,
        query: str,
        *,
        scope: SearchScope | None = None,
        include_pending: bool = False,
        expand_synonyms: bool = True,
        limit: int = 20,
        offset: int = 0,
        sort: str = "score",
    ) -> list[SearchResult]:
        indexed = self.agent_index.read_entries(self.kb_root)
        entries = [item.entry for item in indexed]
        if include_pending:
            entries.extend(_read_entries_from_dir(self.kb_root / PENDING_DIR))
        return _search_entries(
            entries,
            kb_root=self.kb_root,
            source_dirs=(PUBLISHED_DIR,),
            query=query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def search_human(
        self,
        query: str,
        *,
        scope: SearchScope | None = None,
        expand_synonyms: bool = True,
        limit: int = 20,
        offset: int = 0,
        sort: str = "score",
    ) -> list[SearchResult]:
        indexed = self.human_index.read_entries(self.kb_root)
        return _search_entries(
            [item.entry for item in indexed],
            kb_root=self.kb_root,
            source_dirs=(PUBLISHED_DIR,),
            query=query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def search_research(self, query: str) -> list[SearchResult]:
        return self.research_index.search(query)


def _search_entries(
    entries: list[Entry],
    *,
    kb_root: Path,
    source_dirs: tuple[str, ...],
    query: str,
    scope: SearchScope | None,
    expand_synonyms: bool,
    limit: int,
    offset: int,
    sort: str,
) -> list[SearchResult]:
    scope = scope or {}
    synonym_groups = load_synonym_groups(kb_root / "synonyms.jsonl")
    terms = expand_query_terms(query, synonym_groups, enabled=expand_synonyms)
    rg_paths = _ripgrep_candidate_paths(kb_root, source_dirs, terms)
    del rg_paths  # Candidate discovery is best-effort; correctness is enforced below.
    matched_results: list[tuple[Entry, SearchResult]] = []
    for entry in entries:
        result = _search_result_for(entry, terms=terms, original_query=query, scope=scope)
        if result is not None:
            matched_results.append((entry, result))
    sorted_results = _sort_results(matched_results, sort)
    start = max(offset, 0)
    return sorted_results[start : start + max(limit, 0)]


def _read_entries_from_dir(directory: Path) -> list[Entry]:
    if not directory.exists():
        return []
    entries: list[Entry] = []
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        try:
            entries.append(read_entry(path))
        except (OSError, ValidationError, ValueError) as exc:
            LOGGER.warning("skipping unreadable entry file during search: %s (%s)", path, exc)
    return entries


def _ripgrep_candidate_paths(
    kb_root: Path,
    source_dirs: tuple[str, ...],
    terms: list[str],
) -> set[Path]:
    rg = shutil.which("rg")
    if rg is None:
        return set()
    roots = [(kb_root / dirname).resolve() for dirname in source_dirs]
    roots = [root for root in roots if root.exists()]
    if not roots:
        return set()
    paths: set[Path] = set()
    for term in terms:
        if not term or contains_cjk(term):
            continue
        result = subprocess.run(
            [
                rg,
                "--files-with-matches",
                "--fixed-strings",
                "--ignore-case",
                "--glob",
                "*.md",
                "--",
                term,
                *[str(root) for root in roots],
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in {0, 1}:
            LOGGER.warning("ripgrep search failed for term %r: %s", term, result.stderr.strip())
            continue
        for line in result.stdout.splitlines():
            candidate = Path(line).resolve()
            if any(candidate.is_relative_to(root) for root in roots):
                paths.add(candidate)
    return paths


def _search_result_for(
    entry: Entry,
    *,
    terms: list[str],
    original_query: str,
    scope: SearchScope,
) -> SearchResult | None:
    matched_section_raw = _scope_matched_section(entry, scope)
    if matched_section_raw is _NO_MATCH:
        return None
    matched_section = matched_section_raw if isinstance(matched_section_raw, str) else None
    if not _matches_query(entry, terms):
        return None
    stale = bool(entry.code_binding.stale) if entry.code_binding is not None else False
    return SearchResult(
        {
            "id": entry.id,
            "title": entry.title,
            "entry_type": entry.entry_type.value,
            "module": entry.module,
            "snippet": _snippet(entry, terms, original_query),
            "matched_section": matched_section,
            "credibility": entry.credibility.model_dump(mode="json"),
            "trust_state": entry.trust_state.value,
            "stale": stale,
            "score": _score(entry, terms),
        }
    )


_NO_MATCH = object()


def _scope_matched_section(entry: Entry, scope: SearchScope) -> str | None | object:
    if scope.get("module") not in (None, entry.module):
        return _NO_MATCH
    if scope.get("entry_type") not in (None, entry.entry_type.value):
        return _NO_MATCH
    if scope.get("error_code") is not None and scope["error_code"] not in entry.error_codes:
        return _NO_MATCH
    if scope.get("claim_type") not in (None, entry.credibility.claim_type.value):
        return _NO_MATCH
    if scope.get("status") not in (None, entry.trust_state.value):
        return _NO_MATCH
    if scope.get("exclude_stale") and entry.code_binding is not None and entry.code_binding.stale:
        return _NO_MATCH
    min_support = scope.get("min_support")
    if min_support is None:
        return None
    return _support_match(entry, min_support)


def _support_match(entry: Entry, min_support: str) -> str | None | object:
    minimum = SUPPORT_RANK.get(min_support)
    if minimum is None:
        return _NO_MATCH
    if SUPPORT_RANK[entry.credibility.support_strength.value] >= minimum:
        return None
    for section, credibility in entry.section_credibility.items():
        support = credibility.support_strength
        if support is not None and SUPPORT_RANK[support.value] >= minimum:
            return section
    return _NO_MATCH


def _matches_query(entry: Entry, terms: list[str]) -> bool:
    if terms == [""]:
        return True
    text = _entry_search_text(entry)
    return any(_term_matches_text(term, text) for term in terms)


def _entry_search_text(entry: Entry) -> str:
    parts = [
        entry.id,
        entry.title,
        entry.module,
        entry.body,
        *entry.tags,
        *entry.aliases,
        *entry.symptom_keywords,
        *entry.error_codes,
        *entry.log_signatures,
    ]
    return "\n".join(parts).lower()


def _term_matches_text(term: str, text: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return True
    return normalized in text or cjk_bigram_match(normalized, text)


def _snippet(entry: Entry, terms: list[str], original_query: str) -> str:
    lines = [entry.title, *entry.body.splitlines()]
    for term in [original_query, *terms]:
        normalized = term.strip().lower()
        if not normalized:
            continue
        for line in lines:
            if normalized in line.lower() or cjk_bigram_match(normalized, line):
                return line.strip()[:240]
    return entry.title[:240]


def _score(entry: Entry, terms: list[str]) -> int:
    if terms == [""]:
        return 0
    title = entry.title.lower()
    module = entry.module.lower()
    body = entry.body.lower()
    score = 0
    for term in terms:
        normalized = term.strip().lower()
        if not normalized:
            continue
        if normalized in title:
            score += 10
        if normalized in module:
            score += 4
        if normalized in body:
            score += 2
        if any(normalized in value.lower() for value in entry.tags + entry.aliases):
            score += 3
        if any(normalized in value.lower() for value in entry.error_codes):
            score += 5
        if cjk_bigram_match(normalized, _entry_search_text(entry)):
            score += 1
    return score


def _sort_results(results: list[tuple[Entry, SearchResult]], sort: str) -> list[SearchResult]:
    if sort == "updated_desc":
        return [
            result
            for _, result in sorted(
                results, key=lambda item: (item[0].updated, item[0].id), reverse=True
            )
        ]
    if sort == "title":
        return [result for _, result in sorted(results, key=lambda item: item[1]["title"])]
    return [
        result
        for _, result in sorted(
            results,
            key=lambda item: (item[1].get("score", 0), item[0].updated, item[0].id),
            reverse=True,
        )
    ]
