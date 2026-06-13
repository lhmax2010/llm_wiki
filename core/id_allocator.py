"""SQLite-backed KB ID allocator."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ID_PATTERN = re.compile(r"\bKB-(?P<year>\d{4})-(?P<number>\d{4})\b")
FRONTMATTER_ID_PATTERN = re.compile(
    r"(?m)^id:\s*[\"']?(?P<id>KB-(?P<year>\d{4})-(?P<number>\d{4}))[\"']?\s*$"
)
ID_STATE_DIRS = ("entries", "staging", "drafts", "deprecated")
FRONTMATTER_MARKER = "---\n"
MIN_YEAR = 1000
MAX_YEAR = 9999
MAX_ID_NUMBER = 9999


class IDAllocator:
    """Allocate `KB-{year}-{NNNN}` IDs with SQLite transactional uniqueness."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def allocate(self, year: int | None = None) -> str:
        actual_year = year or datetime.now(UTC).year
        _validate_year(actual_year)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT next_number FROM kb_id_sequence WHERE year = ?",
                (actual_year,),
            ).fetchone()
            if row is None:
                number = 1
                conn.execute(
                    "INSERT INTO kb_id_sequence(year, next_number) VALUES (?, ?)",
                    (actual_year, 2),
                )
            else:
                number = int(row[0])
                _validate_number_available(number, actual_year)
                conn.execute(
                    "UPDATE kb_id_sequence SET next_number = ? WHERE year = ?",
                    (number + 1, actual_year),
                )
            conn.commit()
        return f"KB-{actual_year}-{number:04d}"

    def rebuild_from_kb(self, kb_root: Path) -> dict[int, int]:
        """Seed next numbers from official-ID directories and return seed map."""

        max_numbers: dict[int, int] = {}
        for dirname in ID_STATE_DIRS:
            state_dir = kb_root / dirname
            if not state_dir.exists():
                continue
            for path in state_dir.rglob("*"):
                if not path.is_file():
                    continue
                entry_id = _extract_frontmatter_id(path)
                if entry_id is None:
                    continue
                match = ID_PATTERN.fullmatch(entry_id)
                if match is None:
                    continue
                year = int(match.group("year"))
                number = int(match.group("number"))
                max_numbers[year] = max(max_numbers.get(year, 0), number)

        seeds = {year: number + 1 for year, number in max_numbers.items()}
        effective: dict[int, int] = {}
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for year, next_number in seeds.items():
                row = conn.execute(
                    "SELECT next_number FROM kb_id_sequence WHERE year = ?",
                    (year,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO kb_id_sequence(year, next_number) VALUES (?, ?)",
                        (year, next_number),
                    )
                    effective[year] = next_number
                else:
                    preserved = max(int(row[0]), next_number)
                    conn.execute(
                        "UPDATE kb_id_sequence SET next_number = ? WHERE year = ?",
                        (preserved, year),
                    )
                    effective[year] = preserved
            conn.commit()
        return effective

    def next_number_for_year(self, year: int) -> int | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT next_number FROM kb_id_sequence WHERE year = ?",
                (year,),
            ).fetchone()
        return None if row is None else int(row[0])

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_id_sequence (
                    year INTEGER PRIMARY KEY,
                    next_number INTEGER NOT NULL CHECK(next_number > 0)
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _extract_frontmatter_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"entry frontmatter is not valid UTF-8: {path}") from exc
    if not text.startswith(FRONTMATTER_MARKER):
        return None
    parts = text.split(FRONTMATTER_MARKER, 2)
    if len(parts) < 3:
        return None
    match = FRONTMATTER_ID_PATTERN.search(parts[1])
    return None if match is None else match.group("id")


def _validate_year(year: int) -> None:
    if year < MIN_YEAR or year > MAX_YEAR:
        raise ValueError(f"year must be a four-digit year: {year}")


def _validate_number_available(number: int, year: int) -> None:
    if number > MAX_ID_NUMBER:
        raise ValueError(f"KB ID sequence exhausted for {year}")
