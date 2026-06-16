"""Rebuild Phase 4 search indexes."""

from __future__ import annotations

import argparse
from pathlib import Path

from index.search import SearchService


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild unified-kb search indexes")
    parser.add_argument("--kb-root", type=Path, default=Path("kb"))
    args = parser.parse_args()

    service = SearchService(args.kb_root)
    results = [
        service.rebuild_agent_index(),
        service.rebuild_human_index(),
        service.rebuild_research_index(),
    ]
    for result in results:
        print(
            f"{result.index_name}: {result.status}, "
            f"indexed={result.indexed_entries}, skipped={result.skipped_files}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
