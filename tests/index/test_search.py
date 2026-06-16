from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Entry
from core.storage import write_entry
from index.search import SearchService
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


def test_research_index_is_placeholder_and_does_not_scan_research(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "research-only-token"
    _write_payload(kb_root, "research", research)

    result = service.rebuild_research_index()

    assert result.status == "placeholder"
    assert result.indexed_entries == 0
    assert service.search_research("research-only-token") == []
    assert not (kb_root / "indexes" / "research_search_index" / "metadata.sqlite").exists()


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


def test_scope_error_code_exact_match_uses_metadata_filter(tmp_path: Path) -> None:
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


def _write_synonyms(kb_root: Path) -> None:
    kb_root.mkdir(parents=True, exist_ok=True)
    (kb_root / "synonyms.jsonl").write_text(
        '{"canonical": "花屏", "synonyms": ["绿屏", "画面错乱"]}\n',
        encoding="utf-8",
    )


def _write_payload(kb_root: Path, dirname: str, payload: dict[str, Any]) -> None:
    path = kb_root / dirname / f"{payload['id']}.md"
    write_entry(path, Entry.model_validate(payload))
