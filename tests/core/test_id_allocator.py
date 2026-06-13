from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.id_allocator import IDAllocator


def test_allocate_ids_are_unique_under_concurrency(tmp_path: Path) -> None:
    allocator = IDAllocator(tmp_path / "kb" / "indexes" / "ids.sqlite")

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda _: allocator.allocate(2026), range(40)))

    assert len(ids) == len(set(ids))
    assert sorted(ids) == [f"KB-2026-{number:04d}" for number in range(1, 41)]


def test_rebuild_scans_official_id_dirs_including_deprecated(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry_stub(kb_root / "entries" / "low.md", "KB-2026-0002")
    _write_entry_stub(kb_root / "deprecated" / "highest.md", "KB-2026-0042")
    _write_entry_stub(kb_root / "research" / "ignored.md", "KB-2026-9999")

    allocator = IDAllocator(kb_root / "indexes" / "ids.sqlite")
    seeds = allocator.rebuild_from_kb(kb_root)

    assert seeds == {2026: 43}
    assert allocator.allocate(2026) == "KB-2026-0043"
    assert allocator.next_number_for_year(2099) is None


def test_rebuild_does_not_lower_existing_sequence(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry_stub(kb_root / "entries" / "low.md", "KB-2026-0002")
    allocator = IDAllocator(kb_root / "indexes" / "ids.sqlite")

    for _ in range(10):
        allocator.allocate(2026)
    seeds = allocator.rebuild_from_kb(kb_root)

    assert seeds == {2026: 11}
    assert allocator.allocate(2026) == "KB-2026-0011"


def test_rebuild_ignores_referenced_ids_outside_frontmatter_id(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    path = kb_root / "entries" / "entry.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nid: KB-2026-0002\n---\nrelated: KB-2026-0999\n",
        encoding="utf-8",
    )

    allocator = IDAllocator(kb_root / "indexes" / "ids.sqlite")
    allocator.rebuild_from_kb(kb_root)

    assert allocator.allocate(2026) == "KB-2026-0003"


def test_rebuild_fails_on_non_utf8_entry_file(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    path = kb_root / "entries" / "bad.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"---\nid: KB-2026-0009\n---\n\xff")
    allocator = IDAllocator(kb_root / "indexes" / "ids.sqlite")

    with pytest.raises(ValueError, match="valid UTF-8"):
        allocator.rebuild_from_kb(kb_root)


def test_allocator_refuses_ids_outside_schema_range(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_entry_stub(kb_root / "entries" / "last.md", "KB-2026-9999")
    allocator = IDAllocator(kb_root / "indexes" / "ids.sqlite")
    allocator.rebuild_from_kb(kb_root)

    with pytest.raises(ValueError, match="exhausted"):
        allocator.allocate(2026)
    with pytest.raises(ValueError, match="four-digit year"):
        allocator.allocate(10000)


def _write_entry_stub(path: Path, entry_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {entry_id}\n---\nbody\n", encoding="utf-8")
