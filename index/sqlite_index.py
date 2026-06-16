"""SQLite path catalog for Phase 4 search.

P4 uses SQLite to persist a rebuildable list of validated entry paths per search
index. Query-time filtering intentionally stays in Python so synonyms, CJK
bigram matching, and section support passthrough share one correctness path.
SQL-level acceleration is a future optimization once the search surface grows
beyond the V1 thousand-entry budget.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from core.models import Entry
from core.storage import read_entry
from core.validation import validate_entry

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
        for source_dir in self.source_dirs:
            source_entries, source_skipped = read_valid_entries_from_source(
                kb_root, source_dir, context=f"{self.name} rebuild"
            )
            entries.extend(source_entries)
            skipped += source_skipped

        with closing(sqlite3.connect(self.db_path)) as connection:
            _create_schema(connection)
            connection.execute("DELETE FROM index_meta")
            connection.execute("DELETE FROM entries")
            connection.execute(
                "INSERT INTO index_meta(name, status, indexed_at) VALUES (?, ?, ?)",
                (self.name, "ready", datetime.now(UTC).isoformat()),
            )
            connection.executemany(
                """
                INSERT INTO entries(
                    id, path, source_dir
                )
                VALUES (?, ?, ?)
                """,
                [_row_for_entry(item, kb_root) for item in entries],
            )
            connection.commit()

        return IndexBuildResult(
            index_name=self.name,
            indexed_entries=len(entries),
            skipped_files=skipped,
            status="ready",
        )

    def read_entries(self, kb_root: Path) -> list[IndexedEntry]:
        if not self.db_path.is_file():
            raise IndexUnavailable(f"index is not built: {self.name}")
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT path, source_dir FROM entries ORDER BY id"
                ).fetchall()
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
            indexed_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS entries(
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            source_dir TEXT NOT NULL
        )
        """
    )


def _row_for_entry(item: IndexedEntry, kb_root: Path) -> tuple[str, str, str]:
    entry = item.entry
    relative_path = item.path.resolve().relative_to(kb_root.resolve()).as_posix()
    return (entry.id, relative_path, item.source_dir)


def read_valid_entries_from_source(
    kb_root: Path,
    source_dir: str,
    *,
    context: str,
) -> tuple[list[IndexedEntry], int]:
    directory = _safe_source_dir(kb_root, source_dir)
    if not directory.exists():
        return [], 0
    entries: list[IndexedEntry] = []
    skipped = 0
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        item = read_valid_entry_file(kb_root, source_dir, path, context=context)
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
