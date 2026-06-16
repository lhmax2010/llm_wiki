"""SQLite metadata index for Phase 4 search."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from core.models import Entry
from core.storage import read_entry

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
    """Rebuildable SQLite metadata index backed by markdown Entry files."""

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
            directory = _safe_source_dir(kb_root, source_dir)
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.md")):
                if not path.is_file():
                    continue
                try:
                    entry = read_entry(path)
                except (OSError, ValidationError, ValueError) as exc:
                    skipped += 1
                    LOGGER.warning(
                        "skipping unreadable entry file while indexing: %s (%s)", path, exc
                    )
                    continue
                entries.append(IndexedEntry(entry=entry, path=path, source_dir=source_dir))

        with sqlite3.connect(self.db_path) as connection:
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
                    id, path, source_dir, title, module, entry_type, trust_state,
                    claim_type, support_strength, stale, updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_row_for_entry(item, kb_root) for item in entries],
            )

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
            with sqlite3.connect(self.db_path) as connection:
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
            source_root = _safe_source_dir(kb_root, source_dir).resolve()
            if not path.is_relative_to(source_root):
                LOGGER.warning("skipping indexed path outside source dir: %s", path)
                continue
            try:
                entries.append(
                    IndexedEntry(entry=read_entry(path), path=path, source_dir=source_dir)
                )
            except (OSError, ValidationError, ValueError) as exc:
                LOGGER.warning("skipping unreadable indexed entry file: %s (%s)", path, exc)
        return entries

    def indexed_paths(self) -> list[str]:
        if not self.db_path.is_file():
            return []
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute("SELECT path FROM entries ORDER BY path").fetchall()
        return [str(row[0]) for row in rows]


def _create_schema(connection: sqlite3.Connection) -> None:
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
            source_dir TEXT NOT NULL,
            title TEXT NOT NULL,
            module TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            trust_state TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            support_strength TEXT NOT NULL,
            stale INTEGER NOT NULL,
            updated TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_entries_module ON entries(module)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_entries_entry_type ON entries(entry_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_entries_claim_type ON entries(claim_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_entries_trust_state ON entries(trust_state)")


def _row_for_entry(
    item: IndexedEntry, kb_root: Path
) -> tuple[str, str, str, str, str, str, str, str, str, int, str]:
    entry = item.entry
    stale = bool(entry.code_binding.stale) if entry.code_binding is not None else False
    relative_path = item.path.resolve().relative_to(kb_root.resolve()).as_posix()
    return (
        entry.id,
        relative_path,
        item.source_dir,
        entry.title,
        entry.module,
        entry.entry_type.value,
        entry.trust_state.value,
        entry.credibility.claim_type.value,
        entry.credibility.support_strength.value,
        1 if stale else 0,
        entry.updated,
    )


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
