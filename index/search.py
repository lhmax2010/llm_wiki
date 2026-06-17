"""Search service built on Phase 4 validated path indexes.

The current search path optimizes for correctness and isolation: rebuild stores
only validated, source-whitelisted paths, then queries re-read entries and apply
Python filtering. This keeps synonym expansion, CJK bigram matching, and
min_support section passthrough consistent across indexed search and fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.models import Entry
from index.cjk import cjk_bigram_match
from index.sqlite_index import (
    IndexBuildResult,
    IndexUnavailable,
    SQLiteMetadataIndex,
    read_valid_entries_from_source,
)
from index.synonyms import expand_query_terms, load_synonym_groups
from index.types import ResearchSignal, SearchResult, SearchScope
from research.store import (
    ResearchRecord,
    read_valid_research_from_source,
    read_valid_research_record_file,
)

LOGGER = logging.getLogger(__name__)
SUPPORT_RANK = {"weak": 0, "moderate": 1, "strong": 2}
PUBLISHED_DIR = "entries"
PENDING_DIR = "staging"


@dataclass(frozen=True, slots=True)
class ResearchSearchIndex:
    """Physically isolated research search index."""

    name: str = "research_search_index"
    db_path: Path | None = None

    def rebuild(self, kb_root: Path) -> IndexBuildResult:
        db_path = self._db_path(kb_root)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        records, skipped = read_valid_research_from_source(kb_root, context=f"{self.name} rebuild")
        import sqlite3
        from contextlib import closing
        from datetime import UTC, datetime

        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("DROP TABLE IF EXISTS index_meta")
            connection.execute("DROP TABLE IF EXISTS research")
            connection.execute(
                """
                CREATE TABLE index_meta(
                    name TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    indexed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE research(
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO index_meta(name, status, indexed_at) VALUES (?, ?, ?)",
                (self.name, "ready", datetime.now(UTC).isoformat()),
            )
            connection.executemany(
                "INSERT INTO research(id, path) VALUES (?, ?)",
                [
                    (
                        item.record.id,
                        item.path.resolve().relative_to(kb_root.resolve()).as_posix(),
                    )
                    for item in records
                ],
            )
            connection.commit()
        return IndexBuildResult(
            index_name=self.name,
            indexed_entries=len(records),
            skipped_files=skipped,
            status="ready",
        )

    def search(
        self,
        kb_root: Path,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        expand_synonyms: bool = True,
    ) -> list[ResearchSignal]:
        try:
            records = self.read_records(kb_root)
        except IndexUnavailable as exc:
            LOGGER.warning("research index unavailable, falling back to research scan: %s", exc)
            records = [
                item.record
                for item in read_valid_research_from_source(
                    kb_root, context="research direct search"
                )[0]
            ]
        return _search_research_records(
            records,
            kb_root=kb_root,
            query=query,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
        )

    def read_records(self, kb_root: Path) -> list[ResearchRecord]:
        db_path = self._db_path(kb_root)
        if not db_path.is_file():
            raise IndexUnavailable(f"index is not built: {self.name}")
        import sqlite3
        from contextlib import closing

        try:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute("SELECT path FROM research ORDER BY id").fetchall()
        except sqlite3.Error as exc:
            raise IndexUnavailable(f"index is unreadable: {self.name}") from exc
        records: list[ResearchRecord] = []
        for row in rows:
            path = (kb_root / str(row["path"])).resolve()
            item = read_valid_research_record_file(
                kb_root,
                path,
                context=f"{self.name} indexed read",
            )
            if item is not None:
                records.append(item.record)
        return records

    def _db_path(self, kb_root: Path) -> Path:
        return self.db_path or kb_root / "indexes" / self.name / "metadata.sqlite"


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
        return ResearchSearchIndex(
            db_path=self.kb_root / "indexes" / "research_search_index" / "metadata.sqlite"
        )

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
            entries.extend(self._read_source_entries(PENDING_DIR))
        return _search_entries(
            entries,
            kb_root=self.kb_root,
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
            query=query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def search_human_direct(
        self,
        query: str,
        *,
        scope: SearchScope | None = None,
        expand_synonyms: bool = True,
        limit: int = 20,
        offset: int = 0,
        sort: str = "score",
    ) -> list[SearchResult]:
        entries = self._read_source_entries(PUBLISHED_DIR)
        return _search_entries(
            entries,
            kb_root=self.kb_root,
            query=query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def search_agent_direct(
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
        entries = self._read_source_entries(PUBLISHED_DIR)
        if include_pending:
            entries.extend(self._read_source_entries(PENDING_DIR))
        return _search_entries(
            entries,
            kb_root=self.kb_root,
            query=query,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def search_research(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        expand_synonyms: bool = True,
    ) -> list[ResearchSignal]:
        return self.research_index.search(
            self.kb_root,
            query,
            limit=limit,
            offset=offset,
            expand_synonyms=expand_synonyms,
        )

    def _read_source_entries(self, source_dir: str) -> list[Entry]:
        try:
            indexed, _ = read_valid_entries_from_source(
                self.kb_root, source_dir, context=f"{source_dir} direct search"
            )
        except ValueError as exc:
            raise IndexUnavailable(f"invalid search source dir: {source_dir}") from exc
        return [item.entry for item in indexed]


def _search_entries(
    entries: list[Entry],
    *,
    kb_root: Path,
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
    matched_results: list[tuple[Entry, SearchResult]] = []
    for entry in entries:
        result = _search_result_for(entry, terms=terms, original_query=query, scope=scope)
        if result is not None:
            matched_results.append((entry, result))
    sorted_results = _sort_results(matched_results, sort)
    start = max(offset, 0)
    return sorted_results[start : start + max(limit, 0)]


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


def _search_research_records(
    records: list[ResearchRecord],
    *,
    kb_root: Path,
    query: str,
    expand_synonyms: bool,
    limit: int,
    offset: int,
) -> list[ResearchSignal]:
    synonym_groups = load_synonym_groups(kb_root / "synonyms.jsonl")
    terms = expand_query_terms(query, synonym_groups, enabled=expand_synonyms)
    signals = [
        (
            _research_score(record, terms),
            record.created,
            record.id,
            _research_signal_for(record, terms=terms, original_query=query),
        )
        for record in records
        if _research_matches_query(record, terms)
    ]
    signals.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    start = max(offset, 0)
    return [signal for *_sort_keys, signal in signals[start : start + max(limit, 0)]]


def _research_matches_query(record: ResearchRecord, terms: list[str]) -> bool:
    if terms == [""]:
        return True
    text = _research_search_text(record)
    return any(_term_matches_text(term, text) for term in terms)


def _research_search_text(record: ResearchRecord) -> str:
    parts = [record.id, record.title, record.module, record.body, *record.tags]
    return "\n".join(parts).lower()


def _research_signal_for(
    record: ResearchRecord,
    *,
    terms: list[str],
    original_query: str,
) -> ResearchSignal:
    return ResearchSignal(
        {
            "id": record.id,
            "title": record.title,
            "snippet": _research_snippet(record, terms, original_query),
            "trust_state": "research",
            "warning": "unverified_research，不可用于判责",
        }
    )


def _research_snippet(record: ResearchRecord, terms: list[str], original_query: str) -> str:
    lines = [record.title, *record.body.splitlines()]
    for term in [original_query, *terms]:
        normalized = term.strip().lower()
        if not normalized:
            continue
        for line in lines:
            if normalized in line.lower() or cjk_bigram_match(normalized, line):
                return line.strip()[:240]
    return record.title[:240]


def _research_score(record: ResearchRecord, terms: list[str]) -> int:
    if terms == [""]:
        return 0
    title = record.title.lower()
    body = record.body.lower()
    score = 0
    for term in terms:
        normalized = term.strip().lower()
        if not normalized:
            continue
        if normalized in title:
            score += 10
        if normalized in body:
            score += 2
        if any(normalized in tag.lower() for tag in record.tags):
            score += 3
        if cjk_bigram_match(normalized, _research_search_text(record)):
            score += 1
    return score
