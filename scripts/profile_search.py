"""Measure where search time actually goes, phase by phase.

Read-only. Touches nothing but the clock -- no writes to entries/, indexes/, or
anywhere else. Safe to run against a live KB.

The question it answers: of one search, how much is spent pulling paths out of
SQLite, how much reading and validating the entry files, and how much matching
and scoring in Python.

Usage (from the repo root)::

    python scripts/profile_search.py
    python scripts/profile_search.py --query 花屏 --repeat 7
    python scripts/profile_search.py --synth 1000        # temp KB, real one untouched
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from contextlib import closing, suppress
from dataclasses import dataclass, field
from pathlib import Path

# Mirrors `pythonpath = [".", "governed-api"]` in pyproject.toml. governed_api
# lives in a hyphenated directory, so it is not importable without this.
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(_REPO_ROOT / "governed-api"), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import index.search as search_module  # noqa: E402
import index.sqlite_index as sqlite_module  # noqa: E402
from index import SearchService  # noqa: E402
from index.synonyms import load_synonym_groups  # noqa: E402

# A Windows console defaults to a legacy codepage (cp936/cp949/...), which
# cannot encode CJK queries and would abort the run on the first print.
for _stream in (sys.stdout, sys.stderr):
    with suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


@dataclass
class Phase:
    """Accumulated wall-clock for one phase, plus how many times it ran."""

    seconds: float = 0.0
    calls: int = 0

    def add(self, elapsed: float) -> None:
        self.seconds += elapsed
        self.calls += 1


@dataclass
class Counters:
    read_entry: Phase = field(default_factory=Phase)
    validate_entry: Phase = field(default_factory=Phase)

    def reset(self) -> None:
        self.read_entry = Phase()
        self.validate_entry = Phase()


COUNTERS = Counters()


def install_probes() -> None:
    """Wrap the two per-file costs so they can be attributed separately.

    Both names are patched where they are *used* (index.sqlite_index), not
    where they are defined, because that module imported them by value.
    """
    real_read = sqlite_module.read_entry
    real_validate = sqlite_module.validate_entry

    def timed_read(path: Path):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        try:
            return real_read(path)
        finally:
            COUNTERS.read_entry.add(time.perf_counter() - start)

    def timed_validate(entry, **kwargs):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        try:
            return real_validate(entry, **kwargs)
        finally:
            COUNTERS.validate_entry.add(time.perf_counter() - start)

    sqlite_module.read_entry = timed_read
    sqlite_module.validate_entry = timed_validate


def time_sqlite_select(db_path: Path, repeat: int) -> list[float]:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        with closing(sqlite3.connect(db_path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("SELECT path, source_dir FROM entries ORDER BY id").fetchall()
        samples.append(time.perf_counter() - start)
    return samples


def summarize(name: str, samples: list[float], *, total: float | None = None) -> None:
    if not samples:
        print(f"  {name:<34} (no samples)")
        return
    median = statistics.median(samples)
    share = f"  {median / total * 100:5.1f}%" if total else ""
    print(f"  {name:<34} median {median * 1000:9.2f} ms   min {min(samples) * 1000:9.2f} ms{share}")


def build_synthetic_kb(count: int) -> Path:
    """Generate a throwaway KB so scaling can be measured without real data."""
    from core.models import Entry
    from core.storage import write_entry

    root = Path(tempfile.mkdtemp(prefix="kb-profile-"))
    kb_root = root / "kb"
    modules = ["photo", "decoder", "audio", "network", "power"]
    body = (
        "## 现象\n画面出现异常，偶尔卡顿。\n\n"
        "## 环境\n特殊型号设备\n\n"
        "## 根因\n识别逻辑错误导致走错分支\n\n"
        "## 解决方案\n采用正确的识别方法\n\n"
        "## 验证方法\n图像正常显示\n\n"
        "## 经验教训\n读取尺寸判断类型更准确\n"
    )
    for number in range(1, count + 1):
        payload = {
            "schema_version": 3,
            "id": f"KB-2026-{number:04d}",
            "entry_type": "defect_case",
            "title": f"Synthetic defect {number} 花屏",
            "summary": f"Synthetic summary {number}",
            "module": modules[number % len(modules)],
            "credibility": {
                "claim_type": "observation",
                "support_strength": "strong",
                "evidence": [{"type": "human_note", "excerpt": "Observed by reviewer."}],
            },
            "trust_state": "published",
            "author_type": "human",
            "created": "2026-06-15T00:00:00Z",
            "updated": "2026-06-15T00:00:00Z",
            "body": body,
            "tags": ["synthetic", modules[number % len(modules)]],
            "error_codes": [str(-(number % 7))],
        }
        write_entry(kb_root / "entries" / f"KB-2026-{number:04d}.md", Entry.model_validate(payload))
    return kb_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile unified-kb search phases")
    parser.add_argument("--kb-root", type=Path, default=Path("kb"))
    parser.add_argument("--query", default="花屏")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument(
        "--index",
        choices=("human", "agent"),
        default="human",
        help="which index to profile (they are configured identically)",
    )
    parser.add_argument(
        "--synth",
        type=int,
        default=0,
        help="build a temporary KB with N entries instead of using --kb-root",
    )
    args = parser.parse_args()

    temp_kb: Path | None = None
    kb_root: Path = args.kb_root
    if args.synth:
        temp_kb = build_synthetic_kb(args.synth)
        kb_root = temp_kb
        print(f"synthetic KB with {args.synth} entries at {kb_root}")

    try:
        return run(kb_root, args)
    finally:
        if temp_kb is not None:
            shutil.rmtree(temp_kb.parent, ignore_errors=True)


def run(kb_root: Path, args: argparse.Namespace) -> int:
    if not (kb_root / "entries").is_dir():
        print(f"error: no entries/ under {kb_root}", file=sys.stderr)
        return 2

    service = SearchService(kb_root)
    index_obj = service.human_index if args.index == "human" else service.agent_index

    if not index_obj.db_path.is_file():
        print(f"index not built at {index_obj.db_path}")
        print("building it now so the indexed path can be measured...")
        (service.rebuild_human_index if args.index == "human" else service.rebuild_agent_index)()

    entry_count = len(list((kb_root / "entries").glob("*.md")))
    indexed_count = len(index_obj.indexed_paths())
    print(f"\nkb_root={kb_root}  index={args.index}")
    print(f"files in entries/: {entry_count}   paths in index: {indexed_count}")
    if entry_count != indexed_count:
        print("  NOTE: counts differ -- index is stale; rebuild for a fair measurement")
    print(f"query={args.query!r}  repeat={args.repeat}\n")

    install_probes()

    # --- end to end ------------------------------------------------------
    def run_search(scope: dict[str, str] | None = None) -> int:
        if args.index == "human":
            return len(service.search_human(args.query, scope=scope))
        return len(service.search_agent(args.query, scope=scope))

    e2e: list[float] = []
    hits = 0
    for _ in range(args.repeat):
        start = time.perf_counter()
        hits = run_search()
        e2e.append(time.perf_counter() - start)
    total = statistics.median(e2e)

    print("END TO END")
    summarize("search (full call)", e2e)
    print(f"  hits: {hits}\n")

    # --- phase 1: SQLite SELECT -----------------------------------------
    print("PHASE 1  pull path list out of SQLite")
    select_samples = time_sqlite_select(index_obj.db_path, args.repeat)
    summarize("SELECT path, source_dir", select_samples, total=total)

    # --- phase 2: read + validate every file -----------------------------
    read_samples: list[float] = []
    per_read: list[float] = []
    per_validate: list[float] = []
    entries = []
    for _ in range(args.repeat):
        COUNTERS.reset()
        start = time.perf_counter()
        indexed = index_obj.read_entries(kb_root)
        read_samples.append(time.perf_counter() - start)
        per_read.append(COUNTERS.read_entry.seconds)
        per_validate.append(COUNTERS.validate_entry.seconds)
        entries = [item.entry for item in indexed]

    print("\nPHASE 2  read + validate every indexed file")
    summarize("read_entries (whole phase)", read_samples, total=total)
    summarize("  of which read_entry", per_read, total=total)
    summarize("  of which validate_entry", per_validate, total=total)
    # Whatever is left is path.resolve(strict=True) + containment checks in
    # read_valid_entry_file. On Windows those are syscall-heavy per file.
    leftover = [
        whole - read - validate
        for whole, read, validate in zip(read_samples, per_read, per_validate, strict=True)
    ]
    summarize("  of which path resolve/checks", leftover, total=total)
    print(f"  files read per search: {COUNTERS.read_entry.calls}")

    # --- phase 3: synonyms ----------------------------------------------
    synonym_samples: list[float] = []
    for _ in range(args.repeat):
        start = time.perf_counter()
        load_synonym_groups(kb_root / "synonyms.jsonl")
        synonym_samples.append(time.perf_counter() - start)

    print("\nPHASE 3  load + parse synonyms.jsonl (happens every search)")
    summarize("load_synonym_groups", synonym_samples, total=total)

    # --- phase 4: match / score / sort -----------------------------------
    match_samples: list[float] = []
    for _ in range(args.repeat):
        start = time.perf_counter()
        search_module._search_entries(
            entries,
            kb_root=kb_root,
            query=args.query,
            scope=None,
            expand_synonyms=True,
            limit=20,
            offset=0,
            sort="score",
        )
        match_samples.append(time.perf_counter() - start)

    print("\nPHASE 4  scope filter + match + snippet + score + sort")
    summarize("_search_entries", match_samples, total=total)

    # --- does scope reduce anything? -------------------------------------
    print("\nDOES SCOPE HELP?  (same query, narrowed to one module)")
    modules = sorted({entry.module for entry in entries})
    if modules:
        narrow = {"module": modules[0]}
        scoped: list[float] = []
        scoped_hits = 0
        for _ in range(args.repeat):
            COUNTERS.reset()
            start = time.perf_counter()
            scoped_hits = run_search(narrow)
            scoped.append(time.perf_counter() - start)
        summarize(f"scope=module:{modules[0]}", scoped, total=total)
        print(f"  hits: {scoped_hits}   files still read: {COUNTERS.read_entry.calls}")

    # --- fallback path for comparison ------------------------------------
    direct: list[float] = []
    for _ in range(args.repeat):
        start = time.perf_counter()
        service.search_human_direct(args.query)
        direct.append(time.perf_counter() - start)
    print("\nFALLBACK (no index, direct directory scan) for comparison")
    summarize("search_human_direct", direct, total=total)

    print("\nSUMMARY")
    read_median = statistics.median(read_samples)
    match_median = statistics.median(match_samples)
    print(f"  read+validate : {read_median * 1000:9.2f} ms  ({read_median / total * 100:.1f}%)")
    print(f"  match+score   : {match_median * 1000:9.2f} ms  ({match_median / total * 100:.1f}%)")
    print(f"  per file      : {read_median / max(len(entries), 1) * 1000:9.3f} ms")
    verdict = "READING FILES" if read_median > match_median else "MATCHING/SCORING"
    print(f"  dominant cost : {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
