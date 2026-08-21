from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

import index.search as search_module
from core.models import Entry, EntryType
from core.storage import read_entry, write_entry
from core.validation import headings_for_entry_type
from index.search import SearchService
from index.sqlite_index import IndexUnavailable, SQLiteMetadataIndex
from index.types import SearchResult, SearchScope
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


def test_index_rebuild_keeps_previous_sqlite_when_temp_build_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    _write_payload(
        kb_root,
        "entries",
        entry_payload(
            entry_id="KB-2026-0001",
            trust_state="published",
            title="original-index-token",
        ),
    )
    service.rebuild_human_index()
    assert service.human_index.indexed_paths() == ["entries/KB-2026-0001.md"]

    _write_payload(
        kb_root,
        "entries",
        entry_payload(
            entry_id="KB-2026-0002",
            trust_state="published",
            title="new-index-token",
        ),
    )

    def fail_row(*args: object, **kwargs: object) -> tuple[str, str, str]:
        raise RuntimeError("temp build failed")

    monkeypatch.setattr("index.sqlite_index._row_for_entry", fail_row)

    with pytest.raises(RuntimeError, match="temp build failed"):
        service.rebuild_human_index()

    assert service.human_index.indexed_paths() == ["entries/KB-2026-0001.md"]
    assert [path.name for path in (kb_root / "indexes" / "human_search_index").glob("*.tmp")] == []


def test_index_rebuild_records_freshness_metadata_for_all_md_files(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    _write_payload(
        kb_root,
        "entries",
        entry_payload(
            entry_id="KB-2026-0001",
            trust_state="published",
            title="freshness visible",
        ),
    )
    invalid_path = kb_root / "entries" / "invalid.md"
    invalid_path.write_text("not an entry\n", encoding="utf-8")
    expected_max_mtime_ns = max(
        (kb_root / "entries" / "KB-2026-0001.md").stat().st_mtime_ns,
        invalid_path.stat().st_mtime_ns,
    )

    result = service.rebuild_human_index()

    assert result.indexed_entries == 1
    assert result.skipped_files == 1
    with closing(sqlite3.connect(service.human_index.db_path)) as connection:
        row = connection.execute(
            "SELECT scanned_count, max_mtime_ns FROM index_meta WHERE name = ?",
            ("human_search_index",),
        ).fetchone()
    assert row == (2, expected_max_mtime_ns)
    status = service.human_index.freshness_status(kb_root)
    assert status.supported is True
    assert status.stale is False
    assert status.indexed is not None
    assert status.indexed.scanned_count == 2
    assert status.current.scanned_count == 2


def test_index_freshness_detects_changed_file_mtime(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    _write_payload(
        kb_root,
        "entries",
        entry_payload(
            entry_id="KB-2026-0001",
            trust_state="published",
            title="mtime visible",
        ),
    )
    path = kb_root / "entries" / "KB-2026-0001.md"
    service.rebuild_human_index()
    assert service.human_index.freshness_status(kb_root).stale is False

    updated_mtime_ns = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(updated_mtime_ns, updated_mtime_ns))

    status = service.human_index.freshness_status(kb_root)
    assert status.supported is True
    assert status.stale is True
    assert status.indexed is not None
    assert status.current.max_mtime_ns > status.indexed.max_mtime_ns


def test_old_index_schema_reports_freshness_unsupported_without_failing(
    tmp_path: Path,
) -> None:
    kb_root = tmp_path / "kb"
    db_path = kb_root / "indexes" / "legacy" / "metadata.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "CREATE TABLE index_meta("
            "name TEXT PRIMARY KEY, status TEXT NOT NULL, indexed_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO index_meta(name, status, indexed_at) VALUES (?, ?, ?)",
            ("legacy_index", "ready", "2026-06-16T00:00:00+00:00"),
        )
        connection.execute(
            "CREATE TABLE entries("
            "id TEXT PRIMARY KEY, path TEXT NOT NULL, source_dir TEXT NOT NULL)"
        )
        connection.commit()
    index = SQLiteMetadataIndex(
        name="legacy_index",
        db_path=db_path,
        source_dirs=("entries",),
    )

    status = index.freshness_status(kb_root)

    assert status.supported is False
    assert status.stale is False
    assert status.indexed is None
    assert status.reason == "index_meta freshness columns missing"


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


@pytest.mark.parametrize("target_dir", ["research", "staging", "deprecated"])
def test_agent_index_rebuild_rejects_source_directory_symlink(
    tmp_path: Path,
    target_dir: str,
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    target = kb_root / target_dir
    target.mkdir(parents=True, exist_ok=True)
    link_path = kb_root / "entries"
    try:
        link_path.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this filesystem: {exc}")

    with pytest.raises(ValueError, match="index source dir must not be a symlink"):
        service.rebuild_agent_index()


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
    assert set(signals[0]) == {"id", "title", "snippet", "trust_state", "warning"}
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


def test_module_and_entry_type_pushdown_matches_python_filter_matrix(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    for number, module, entry_type in (
        (1, "photo", "defect_case"),
        (2, "photo", "triage_rule"),
        (3, "decoder", "defect_case"),
        (4, "decoder", "log_baseline"),
    ):
        payload = entry_payload(
            entry_id=f"KB-2026-{number:04d}",
            trust_state="published",
            title=f"scope-token {module} {entry_type}",
            body=body_for(entry_type),
        )
        payload["module"] = module
        payload["entry_type"] = entry_type
        if number == 2:
            payload["credibility"]["support_strength"] = "weak"
            payload["section_credibility"] = {
                headings_for_entry_type(EntryType.TRIAGE_RULE)[0]: {
                    "claim_type": "observation",
                    "support_strength": "strong",
                    "evidence": [],
                }
            }
        _write_payload(kb_root, "entries", payload)
    service.rebuild_agent_index()

    scopes: list[SearchScope] = [
        {},
        {"module": "photo"},
        {"entry_type": "triage_rule"},
        {"module": "photo", "entry_type": "triage_rule"},
        {"module": "photo", "min_support": "strong"},
    ]
    for scope in scopes:
        assert _indexed_search(service, scope=scope, allow_pushdown=True) == _indexed_search(
            service, scope=scope, allow_pushdown=False
        )


def test_stale_scoped_search_falls_back_to_source_scan_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    payload = entry_payload(
        entry_id="KB-2026-0001",
        trust_state="published",
        title="stale-token changed module",
    )
    payload["module"] = "decoder"
    _write_payload(kb_root, "entries", payload)
    other = entry_payload(
        entry_id="KB-2026-0002",
        trust_state="published",
        title="stale-token still decoder",
    )
    other["module"] = "decoder"
    _write_payload(kb_root, "entries", other)
    path = kb_root / "entries" / "KB-2026-0001.md"
    service.rebuild_agent_index()
    old_mtime_ns = path.stat().st_mtime_ns

    payload["module"] = "photo"
    write_entry(path, Entry.model_validate(payload))
    updated_mtime_ns = old_mtime_ns + 1_000_000_000
    os.utime(path, ns=(updated_mtime_ns, updated_mtime_ns))

    results = service.search_agent(
        "stale-token",
        scope={"module": "photo"},
        expand_synonyms=False,
    )

    assert [result["id"] for result in results] == ["KB-2026-0001"]
    assert "agent_search_index is stale" in caplog.text
    assert "falling back to full source scan" in caplog.text


def test_python_scope_recheck_prevents_stale_pushdown_false_positive(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    for number in (1, 2):
        payload = entry_payload(
            entry_id=f"KB-2026-{number:04d}",
            trust_state="published",
            title="subset-token shared",
        )
        payload["module"] = "photo"
        _write_payload(kb_root, "entries", payload)
    service.rebuild_agent_index()
    stale_path = kb_root / "entries" / "KB-2026-0001.md"
    old_mtime_ns = stale_path.stat().st_mtime_ns

    stale_payload = entry_payload(
        entry_id="KB-2026-0001",
        trust_state="published",
        title="subset-token shared",
    )
    stale_payload["module"] = "audio"
    write_entry(stale_path, Entry.model_validate(stale_payload))
    os.utime(stale_path, ns=(old_mtime_ns, old_mtime_ns))
    assert service.agent_index.freshness_status(kb_root).stale is False

    results = service.search_agent(
        "subset-token",
        scope={"module": "photo"},
        expand_synonyms=False,
    )

    assert [result["id"] for result in results] == ["KB-2026-0002"]
    assert all(result["module"] == "photo" for result in results)


def test_old_index_schema_scoped_search_falls_back_to_source_scan(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    photo = entry_payload(
        entry_id="KB-2026-0001",
        trust_state="published",
        title="legacy-token photo",
    )
    photo["module"] = "photo"
    decoder = entry_payload(
        entry_id="KB-2026-0002",
        trust_state="published",
        title="legacy-token decoder",
    )
    decoder["module"] = "decoder"
    _write_payload(kb_root, "entries", photo)
    _write_payload(kb_root, "entries", decoder)
    db_path = service.agent_index.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "CREATE TABLE index_meta("
            "name TEXT PRIMARY KEY, status TEXT NOT NULL, indexed_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO index_meta(name, status, indexed_at) VALUES (?, ?, ?)",
            ("agent_search_index", "ready", "2026-06-16T00:00:00+00:00"),
        )
        connection.execute(
            "CREATE TABLE entries("
            "id TEXT PRIMARY KEY, path TEXT NOT NULL, source_dir TEXT NOT NULL)"
        )
        connection.commit()

    results = service.search_agent(
        "legacy-token",
        scope={"module": "photo"},
        expand_synonyms=False,
    )

    assert [result["id"] for result in results] == ["KB-2026-0001"]


def test_module_pushdown_reads_only_matching_module_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    for number, module in (
        (1, "photo"),
        (2, "photo"),
        (3, "decoder"),
        (4, "decoder"),
        (5, "audio"),
    ):
        payload = entry_payload(
            entry_id=f"KB-2026-{number:04d}",
            trust_state="published",
            title=f"read-count-token {module}",
        )
        payload["module"] = module
        _write_payload(kb_root, "entries", payload)
    service.rebuild_agent_index()
    calls = 0
    real_read_entry = read_entry

    def counted_read_entry(path: Path) -> Entry:
        nonlocal calls
        calls += 1
        return real_read_entry(path)

    monkeypatch.setattr("index.sqlite_index.read_entry", counted_read_entry)

    results = service.search_agent(
        "read-count-token",
        scope={"module": "photo"},
        expand_synonyms=False,
        limit=10,
    )

    assert {result["id"] for result in results} == {"KB-2026-0001", "KB-2026-0002"}
    assert calls == 2


def test_summary_matches_with_priority_between_title_and_error_code(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    title_hit = entry_payload(
        entry_id="KB-2026-0001",
        trust_state="published",
        title="priority-token title hit",
    )
    summary_hit = entry_payload(
        entry_id="KB-2026-0002",
        trust_state="published",
        title="summary-only title",
    )
    summary_hit["summary"] = "priority-token concise root cause sentence."
    error_hit = entry_payload(
        entry_id="KB-2026-0003",
        trust_state="published",
        title="error-code-only title",
    )
    error_hit["error_codes"] = ["priority-token"]
    _write_payload(kb_root, "entries", title_hit)
    _write_payload(kb_root, "entries", summary_hit)
    _write_payload(kb_root, "entries", error_hit)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    results = service.search_agent("priority-token", expand_synonyms=False)

    assert [result["id"] for result in results] == [
        "KB-2026-0001",
        "KB-2026-0002",
        "KB-2026-0003",
    ]
    assert [result["score"] for result in results] == [10, 8, 5]
    assert results[1]["snippet"] == "priority-token concise root cause sentence."


def test_summary_is_default_snippet_when_query_has_no_specific_hit(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    payload["summary"] = "One sentence summary for the entry."
    _write_payload(kb_root, "entries", payload)
    service = SearchService(kb_root)
    service.rebuild_agent_index()

    results = service.search_agent("", expand_synonyms=False)

    assert results[0]["snippet"] == "One sentence summary for the entry."


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


def _indexed_search(
    service: SearchService,
    *,
    scope: SearchScope,
    allow_pushdown: bool,
    query: str = "scope-token",
) -> list[SearchResult]:
    indexed = service.agent_index.read_entries(
        service.kb_root,
        scope=scope,
        allow_pushdown=allow_pushdown,
    )
    return search_module._search_entries(
        [item.entry for item in indexed],
        kb_root=service.kb_root,
        query=query,
        scope=scope,
        expand_synonyms=False,
        limit=20,
        offset=0,
        sort="score",
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
