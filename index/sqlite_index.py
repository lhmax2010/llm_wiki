"""SQLite path catalog for Phase 4 search.

P4 uses SQLite to persist a rebuildable list of validated entry paths per search
index. Query-time correctness stays in Python so synonyms, CJK bigram matching,
and section support passthrough share one path. SQLite may prefilter candidate
paths for simple metadata such as module/entry_type, but every candidate is
still re-read and rechecked by Python before it can be returned.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from core.models import Entry
from core.storage import read_entry
from core.validation import validate_entry
from index.types import SearchScope

LOGGER = logging.getLogger(__name__)
RESEARCH_DIR = "research"


class IndexUnavailable(Exception):
    """Raised when a search index cannot be used and callers should fallback."""


@dataclass(frozen=True, slots=True)
class IndexBuildResult:
    index_name: str
    indexed_entries: int
    skipped_files: int
    status: str


@dataclass(frozen=True, slots=True)
class IndexedEntry:
    entry: Entry
    path: Path
    source_dir: str


@dataclass(frozen=True, slots=True)
class IndexFreshness:
    scanned_count: int
    max_mtime_ns: int


@dataclass(frozen=True, slots=True)
class IndexFreshnessStatus:
    supported: bool
    stale: bool
    current: IndexFreshness
    indexed: IndexFreshness | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    files: tuple[SourceFile, ...]
    freshness: IndexFreshness


@dataclass(frozen=True, slots=True)
class SQLiteMetadataIndex:
    """Rebuildable SQLite path index backed by validated markdown Entry files."""

    name: str
    db_path: Path
    source_dirs: tuple[str, ...]
    allow_research: bool = False

    def __post_init__(self) -> None:
        if not self.allow_research and RESEARCH_DIR in self.source_dirs:
            raise ValueError(f"{self.name} must not index research")

    def rebuild(self, kb_root: Path) -> IndexBuildResult:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        entries: list[IndexedEntry] = []
        skipped = 0
        source_snapshots: list[SourceSnapshot] = []
        for source_dir in self.source_dirs:
            snapshot = scan_source_files(kb_root, source_dir)
            source_snapshots.append(snapshot)
            source_entries, source_skipped = _read_valid_entries_from_files(
                kb_root,
                source_dir,
                snapshot.files,
                context=f"{self.name} rebuild",
            )
            entries.extend(source_entries)
            skipped += source_skipped
        freshness = _combine_freshness(snapshot.freshness for snapshot in source_snapshots)

        temp_path = self.db_path.with_name(f".{self.db_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with closing(sqlite3.connect(temp_path)) as connection:
                _create_schema(connection)
                connection.execute(
                    """
                    INSERT INTO index_meta(
                        name, status, indexed_at, scanned_count, max_mtime_ns
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.name,
                        "ready",
                        datetime.now(UTC).isoformat(),
                        freshness.scanned_count,
                        freshness.max_mtime_ns,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO entries(
                        id, path, source_dir, module, entry_type
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [_row_for_entry(item, kb_root) for item in entries],
                )
                connection.commit()
            temp_path.replace(self.db_path)
        except Exception:
            with suppress(FileNotFoundError):
                temp_path.unlink()
            raise

        return IndexBuildResult(
            index_name=self.name,
            indexed_entries=len(entries),
            skipped_files=skipped,
            status="ready",
        )

    def freshness_status(self, kb_root: Path) -> IndexFreshnessStatus:
        if not self.db_path.is_file():
            raise IndexUnavailable(f"index is not built: {self.name}")
        current = current_freshness(kb_root, self.source_dirs)
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                columns = _table_columns(connection, "index_meta")
                if not {"scanned_count", "max_mtime_ns"}.issubset(columns):
                    return IndexFreshnessStatus(
                        supported=False,
                        stale=False,
                        current=current,
                        indexed=None,
                        reason="index_meta freshness columns missing",
                    )
                row = connection.execute(
                    """
                    SELECT scanned_count, max_mtime_ns
                    FROM index_meta
                    WHERE name = ?
                    """,
                    (self.name,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise IndexUnavailable(f"index is unreadable: {self.name}") from exc
        if row is None:
            raise IndexUnavailable(f"index metadata missing: {self.name}")
        indexed = IndexFreshness(scanned_count=int(row[0]), max_mtime_ns=int(row[1]))
        return IndexFreshnessStatus(
            supported=True,
            stale=indexed != current,
            current=current,
            indexed=indexed,
        )

    def read_entries(
        self,
        kb_root: Path,
        *,
        scope: SearchScope | None = None,
        allow_pushdown: bool = True,
    ) -> list[IndexedEntry]:
        if not self.db_path.is_file():
            raise IndexUnavailable(f"index is not built: {self.name}")
        pushdown_filters = _pushdown_filters(scope or {}) if allow_pushdown else {}
        use_pushdown = False
        if pushdown_filters:
            use_pushdown = self._can_push_down(kb_root)
            if use_pushdown and self._is_stale(kb_root):
                LOGGER.warning(
                    "%s is stale; falling back to full source scan for scoped search",
                    self.name,
                )
                return self._read_source_entries(kb_root)
            if not use_pushdown:
                LOGGER.warning(
                    "%s cannot push down scoped search; falling back to full source scan",
                    self.name,
                )
                return self._read_source_entries(kb_root)
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                connection.row_factory = sqlite3.Row
                rows = _select_entry_rows(connection, pushdown_filters if use_pushdown else {})
        except sqlite3.Error as exc:
            raise IndexUnavailable(f"index is unreadable: {self.name}") from exc

        entries: list[IndexedEntry] = []
        for row in rows:
            path = (kb_root / str(row["path"])).resolve()
            source_dir = str(row["source_dir"])
            try:
                item = read_valid_entry_file(
                    kb_root,
                    source_dir,
                    path,
                    context=f"{self.name} indexed read",
                )
            except ValueError as exc:
                raise IndexUnavailable(f"index has invalid source_dir: {source_dir}") from exc
            if item is not None:
                entries.append(item)
        return entries

    def _can_push_down(self, kb_root: Path) -> bool:
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                entries_columns = _table_columns(connection, "entries")
                meta_columns = _table_columns(connection, "index_meta")
        except sqlite3.Error as exc:
            raise IndexUnavailable(f"index is unreadable: {self.name}") from exc
        has_filter_columns = {"module", "entry_type"}.issubset(entries_columns)
        has_freshness_columns = {"scanned_count", "max_mtime_ns"}.issubset(meta_columns)
        if not has_filter_columns or not has_freshness_columns:
            return False
        try:
            status = self.freshness_status(kb_root)
        except ValueError as exc:
            raise IndexUnavailable(f"invalid index source dir: {self.name}") from exc
        return status.supported

    def _is_stale(self, kb_root: Path) -> bool:
        status = self.freshness_status(kb_root)
        return status.stale

    def _read_source_entries(self, kb_root: Path) -> list[IndexedEntry]:
        entries: list[IndexedEntry] = []
        for source_dir in self.source_dirs:
            source_entries, _ = read_valid_entries_from_source(
                kb_root, source_dir, context=f"{self.name} direct freshness fallback"
            )
            entries.extend(source_entries)
        return entries

    def indexed_paths(self) -> list[str]:
        if not self.db_path.is_file():
            return []
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute("SELECT path FROM entries ORDER BY path").fetchall()
        return [str(row[0]) for row in rows]


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("DROP TABLE IF EXISTS index_meta")
    connection.execute("DROP TABLE IF EXISTS entries")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS index_meta(
            name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            scanned_count INTEGER NOT NULL,
            max_mtime_ns INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS entries(
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            source_dir TEXT NOT NULL,
            module TEXT NOT NULL,
            entry_type TEXT NOT NULL
        )
        """
    )


def _row_for_entry(item: IndexedEntry, kb_root: Path) -> tuple[str, str, str, str, str]:
    entry = item.entry
    relative_path = item.path.resolve().relative_to(kb_root.resolve()).as_posix()
    return (entry.id, relative_path, item.source_dir, entry.module, entry.entry_type.value)


def read_valid_entries_from_source(
    kb_root: Path,
    source_dir: str,
    *,
    context: str,
) -> tuple[list[IndexedEntry], int]:
    snapshot = scan_source_files(kb_root, source_dir)
    return _read_valid_entries_from_files(kb_root, source_dir, snapshot.files, context=context)


def _read_valid_entries_from_files(
    kb_root: Path,
    source_dir: str,
    files: tuple[SourceFile, ...],
    *,
    context: str,
) -> tuple[list[IndexedEntry], int]:
    entries: list[IndexedEntry] = []
    skipped = 0
    for source_file in files:
        item = read_valid_entry_file(kb_root, source_dir, source_file.path, context=context)
        if item is None:
            skipped += 1
            continue
        entries.append(item)
    return entries, skipped


def read_valid_entry_file(
    kb_root: Path,
    source_dir: str,
    path: Path,
    *,
    context: str,
) -> IndexedEntry | None:
    source_root = _safe_source_dir(kb_root, source_dir).resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        LOGGER.warning("%s: skipping unresolvable entry path: %s (%s)", context, path, exc)
        return None
    if not resolved.is_file():
        return None
    if not resolved.is_relative_to(source_root):
        LOGGER.warning("%s: skipping entry path outside source dir: %s", context, resolved)
        return None
    try:
        entry = read_entry(resolved)
    except (OSError, ValidationError, ValueError) as exc:
        LOGGER.warning("%s: skipping unreadable entry file: %s (%s)", context, resolved, exc)
        return None
    report = validate_entry(
        entry,
        kb_root=kb_root,
        entry_path=resolved,
        check_evidence_exists=False,
    )
    if not report.ok:
        issues = "; ".join(
            f"{issue.code.value}:{issue.field}:{issue.message}" for issue in report.errors
        )
        LOGGER.warning("%s: skipping invalid entry file: %s (%s)", context, resolved, issues)
        return None
    return IndexedEntry(entry=report.entry, path=resolved, source_dir=source_dir)


def _safe_source_dir(kb_root: Path, source_dir: str) -> Path:
    if source_dir == RESEARCH_DIR:
        raise ValueError("research source dir is reserved for Phase 6")
    if "/" in source_dir or "\\" in source_dir or source_dir in {"", ".", ".."}:
        raise ValueError(f"invalid index source dir: {source_dir}")
    root = kb_root.resolve()
    directory = (root / source_dir).resolve()
    if not directory.is_relative_to(root):
        raise ValueError(f"index source dir escapes kb root: {source_dir}")
    return directory


def scan_source_files(kb_root: Path, source_dir: str) -> SourceSnapshot:
    directory = _safe_source_dir(kb_root, source_dir)
    if not directory.exists():
        return SourceSnapshot(files=(), freshness=IndexFreshness(0, 0))
    files: list[SourceFile] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if not entry.name.endswith(".md"):
                continue
            try:
                if not entry.is_file(follow_symlinks=True):
                    continue
                stat_result = entry.stat(follow_symlinks=True)
            except OSError:
                files.append(SourceFile(Path(entry.path), 0))
                continue
            files.append(SourceFile(Path(entry.path), stat_result.st_mtime_ns))
    files.sort(key=lambda item: item.path.name)
    freshness = IndexFreshness(
        scanned_count=len(files),
        max_mtime_ns=max((item.mtime_ns for item in files), default=0),
    )
    return SourceSnapshot(files=tuple(files), freshness=freshness)


def current_freshness(kb_root: Path, source_dirs: tuple[str, ...]) -> IndexFreshness:
    snapshots = [scan_source_files(kb_root, source_dir).freshness for source_dir in source_dirs]
    return _combine_freshness(snapshots)


def _combine_freshness(freshnesses: Iterable[IndexFreshness]) -> IndexFreshness:
    items = list(freshnesses)
    return IndexFreshness(
        scanned_count=sum(item.scanned_count for item in items),
        max_mtime_ns=max((item.max_mtime_ns for item in items), default=0),
    )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _pushdown_filters(scope: SearchScope) -> dict[str, str]:
    filters: dict[str, str] = {}
    module = scope.get("module")
    if module is not None:
        filters["module"] = module
    entry_type = scope.get("entry_type")
    if entry_type is not None:
        filters["entry_type"] = entry_type
    return filters


def _select_entry_rows(
    connection: sqlite3.Connection,
    filters: dict[str, str],
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[str] = []
    if "module" in filters:
        clauses.append("module = ?")
        params.append(filters["module"])
    if "entry_type" in filters:
        clauses.append("entry_type = ?")
        params.append(filters["entry_type"])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return connection.execute(
        f"SELECT path, source_dir FROM entries{where} ORDER BY id",
        params,
    ).fetchall()
