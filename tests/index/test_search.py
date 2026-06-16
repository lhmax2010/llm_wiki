from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from core.models import Entry
from core.storage import write_entry
from index.search import SearchService
from index.sqlite_index import IndexUnavailable, SQLiteMetadataIndex
from research.store import ResearchRecord, write_research_record
from tests.governed_api.helpers import body_for, entry_payload


def test_agent_index_rebuild_excludes_research_at_source(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    _write_payload(
        kb_root, "entries", entry_payload(entry_id="KB-2026-0001", trust_state="published")
    )
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "research-only-token"
    _write_payload(kb_root, "research", research)

    result = service.rebuild_agent_index()

    assert result.indexed_entries == 1
    assert all(not path.startswith("research/") for path in service.agent_index.indexed_paths())
    assert service.search_agent("research-only-token") == []


def test_agent_index_rebuild_rejects_symlink_escape_to_research(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "research-only-token"
    _write_payload(kb_root, "research", research)
    link_path = kb_root / "entries" / "KB-2026-0002.md"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(kb_root / "research" / "KB-2026-0002.md")
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this filesystem: {exc}")

    result = service.rebuild_agent_index()

    assert result.indexed_entries == 0
    assert result.skipped_files == 1
    assert service.agent_index.indexed_paths() == []
    assert service.search_agent("research-only-token") == []
    assert "outside source dir" in caplog.text


def test_agent_index_rebuild_skips_entry_with_wrong_trust_state(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="research")
    payload["title"] = "wrong-state-token"
    _write_payload(kb_root, "entries", payload)

    result = service.rebuild_agent_index()

    assert result.indexed_entries == 0
    assert result.skipped_files == 1
    assert service.search_agent("wrong-state-token") == []


def test_research_index_is_real_and_still_separate_from_agent_index(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    _write_research(kb_root, "R-2026-0001", title="research-only-token")

    service.rebuild_agent_index()
    result = service.rebuild_research_index()

    assert result.status == "ready"
    assert result.indexed_entries == 1
    signals = service.search_research("raw research body")
    assert [signal["id"] for signal in signals] == ["R-2026-0001"]
    assert signals[0]["trust_state"] == "research"
    assert signals[0]["warning"] == "unverified_research，不可用于判责"
    assert "raw research body" in signals[0]["snippet"]
    assert "body" not in signals[0]
    assert service.search_agent("research-only-token") == []


def test_synonym_expansion_hits_canonical_entry(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_synonyms(kb_root)
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["title"] = "花屏 defect case"
    _write_payload(kb_root, "entries", payload)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    expanded = service.search_agent("绿屏", expand_synonyms=True)
    unexpanded = service.search_agent("绿屏", expand_synonyms=False)

    assert [result["id"] for result in expanded] == ["KB-2026-0001"]
    assert unexpanded == []


def test_bad_synonym_line_is_skipped_without_disabling_good_lines(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    kb_root = tmp_path / "kb"
    kb_root.mkdir(parents=True, exist_ok=True)
    (kb_root / "synonyms.jsonl").write_text(
        '{bad json}\n{"canonical": "花屏", "synonyms": ["绿屏", "画面错乱"]}\n',
        encoding="utf-8",
    )
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["title"] = "花屏 defect case"
    _write_payload(kb_root, "entries", payload)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    results = service.search_agent("绿屏", expand_synonyms=True)

    assert [result["id"] for result in results] == ["KB-2026-0001"]
    assert "skipping invalid synonym line" in caplog.text


def test_cjk_bigram_query_hits_non_contiguous_chinese_phrase(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    body = body_for().replace("现象 content.", "画面出现绿屏。")
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published", body=body)
    payload["title"] = "Display anomaly"
    _write_payload(kb_root, "entries", payload)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    results = service.search_agent("画面绿屏", expand_synonyms=False)

    assert [result["id"] for result in results] == ["KB-2026-0001"]
    assert results[0]["snippet"] == "画面出现绿屏。"


def test_min_support_matches_section_and_reports_matched_section(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["credibility"]["support_strength"] = "weak"
    payload["section_credibility"] = {
        "根因": {"claim_type": "fact", "support_strength": "strong", "evidence": []}
    }
    _write_payload(kb_root, "entries", payload)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    results = service.search_agent("decoder", scope={"min_support": "strong"})

    assert [result["id"] for result in results] == ["KB-2026-0001"]
    assert results[0]["matched_section"] == "根因"


def test_scope_error_code_exact_match_filters_results(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    matching = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    matching["error_codes"] = ["E_DEC_42"]
    other = entry_payload(entry_id="KB-2026-0002", trust_state="published")
    other["error_codes"] = ["E_OTHER"]
    _write_payload(kb_root, "entries", matching)
    _write_payload(kb_root, "entries", other)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    results = service.search_agent("", scope={"error_code": "E_DEC_42"})

    assert [result["id"] for result in results] == ["KB-2026-0001"]


def test_index_read_entries_normalizes_invalid_source_dir_to_index_unavailable(
    tmp_path: Path,
) -> None:
    kb_root = tmp_path / "kb"
    db_path = kb_root / "indexes" / "bad" / "metadata.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "CREATE TABLE entries("
            "id TEXT PRIMARY KEY, path TEXT NOT NULL, source_dir TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO entries(id, path, source_dir) VALUES (?, ?, ?)",
            ("KB-2026-0001", "entries/KB-2026-0001.md", "../research"),
        )
        connection.commit()
    index = SQLiteMetadataIndex(
        name="bad_index",
        db_path=db_path,
        source_dirs=("entries",),
    )

    with pytest.raises(IndexUnavailable):
        index.read_entries(kb_root)


def test_search_result_preserves_agent_view_fields(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["code_binding"] = {
        "repo_id": "kona",
        "paths": ["decoder/foo.c"],
        "path_hashes": {"decoder/foo.c": "a" * 64},
        "symbol_resolution": "fallback_path",
        "stale": True,
        "stale_reason": "path changed",
    }
    _write_payload(kb_root, "entries", payload)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    result = service.search_agent("decoder")[0]

    assert {
        "id",
        "title",
        "entry_type",
        "module",
        "snippet",
        "matched_section",
        "credibility",
        "trust_state",
        "stale",
        "score",
    }.issubset(result)
    assert result["credibility"]["claim_type"] == "observation"
    assert result["stale"] is True


def test_human_index_interface_is_real_but_still_excludes_research(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    published = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    published["title"] = "Human visible decoder case"
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "research-only-token"
    _write_payload(kb_root, "entries", published)
    _write_payload(kb_root, "research", research)
    service = SearchService(kb_root)

    result = service.rebuild_human_index()

    assert result.indexed_entries == 1
    assert [item["id"] for item in service.search_human("Human visible")] == ["KB-2026-0001"]
    assert service.search_human("research-only-token") == []


def test_research_index_rejects_symlink_escape_to_entries(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    _write_payload(
        kb_root, "entries", entry_payload(entry_id="KB-2026-0001", trust_state="published")
    )
    link_path = kb_root / "research" / "R-2026-0001.md"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(kb_root / "entries" / "KB-2026-0001.md")
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this filesystem: {exc}")

    result = service.rebuild_research_index()

    assert result.indexed_entries == 0
    assert result.skipped_files == 1
    assert service.search_research("Decoder") == []
    assert "outside source dir" in caplog.text


def _write_synonyms(kb_root: Path) -> None:
    kb_root.mkdir(parents=True, exist_ok=True)
    (kb_root / "synonyms.jsonl").write_text(
        '{"canonical": "花屏", "synonyms": ["绿屏", "画面错乱"]}\n',
        encoding="utf-8",
    )


def _write_payload(kb_root: Path, dirname: str, payload: dict[str, Any]) -> None:
    path = kb_root / dirname / f"{payload['id']}.md"
    write_entry(path, Entry.model_validate(payload))


def _write_research(kb_root: Path, research_id: str, *, title: str) -> None:
    write_research_record(
        kb_root / "research" / f"{research_id}.md",
        ResearchRecord(
            id=research_id,
            title=title,
            body=f"raw research body {title}",
            tags=["decoder"],
            created="2026-06-16T00:00:00+00:00",
            updated="2026-06-16T00:00:00+00:00",
            expires_at="2026-08-15T00:00:00+00:00",
        ),
    )
