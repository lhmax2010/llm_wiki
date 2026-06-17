from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.models import Entry
from core.storage import write_entry
from index import SearchService
from research.store import ResearchRecord, write_research_record
from tests.governed_api.helpers import entry_payload
from web_api.app import create_app
from web_api.service import WebApiError, WebReadService, build_scope


def test_search_uses_human_index_and_excludes_research(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    published = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    published["title"] = "Visible decoder case"
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "research-only-token"
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", published)
    _write_payload(kb_root / "research" / "KB-2026-0002.md", research)
    SearchService(kb_root).rebuild_human_index()
    client = TestClient(create_app(kb_root=kb_root))

    visible = client.get("/api/entries", params={"q": "Visible"})
    hidden = client.get("/api/entries", params={"q": "research-only-token"})

    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["entries"]] == ["KB-2026-0001"]
    assert visible.json()["entries"][0]["trust_state"] == "published"
    assert hidden.status_code == 200
    assert hidden.json()["entries"] == []


def test_search_fallback_is_entries_only_when_index_is_unavailable(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    published = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    published["title"] = "Fallback visible case"
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "fallback-research-secret"
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", published)
    _write_payload(kb_root / "research" / "KB-2026-0002.md", research)
    client = TestClient(create_app(kb_root=kb_root))

    visible = client.get("/api/entries", params={"q": "Fallback visible"})
    hidden = client.get("/api/entries", params={"q": "fallback-research-secret"})

    assert [item["id"] for item in visible.json()["entries"]] == ["KB-2026-0001"]
    assert hidden.json()["entries"] == []


def test_get_entry_rejects_traversal_and_never_reads_staging_or_research(
    tmp_path: Path,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "staging" / "KB-2026-0002.md",
        entry_payload(entry_id="KB-2026-0002", trust_state="pending"),
    )
    _write_payload(
        kb_root / "research" / "KB-2026-0003.md",
        entry_payload(entry_id="KB-2026-0003", trust_state="research"),
    )
    client = TestClient(create_app(kb_root=kb_root))

    invalid = client.get("/api/entries/KB-2026-1")
    traversal = client.get("/api/entries/%2E%2E%2Fresearch%2FKB-2026-0003")
    staging = client.get("/api/entries/KB-2026-0002")
    research = client.get("/api/entries/KB-2026-0003")

    assert invalid.status_code == 400
    assert invalid.json()["error"]["field"] == "id"
    assert traversal.status_code in {400, 404}
    assert staging.status_code == 404
    assert research.status_code == 404


def test_get_entry_returns_complete_json_for_published_entry(tmp_path: Path) -> None:
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
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", payload)
    client = TestClient(create_app(kb_root=kb_root))

    response = client.get("/api/entries/KB-2026-0001")

    assert response.status_code == 200
    entry = response.json()["entry"]
    assert entry["credibility"]["claim_type"] == "observation"
    assert entry["code_binding"]["paths"] == ["decoder/foo.c"]
    assert entry["code_binding"]["stale"] is True
    assert "section_credibility" in entry


def test_categories_and_browse_only_use_published_entries(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published", tags=["published-tag"]),
    )
    _write_payload(
        kb_root / "staging" / "KB-2026-0002.md",
        entry_payload(entry_id="KB-2026-0002", trust_state="pending", tags=["pending-secret"]),
    )
    _write_payload(
        kb_root / "research" / "KB-2026-0003.md",
        entry_payload(entry_id="KB-2026-0003", trust_state="research", tags=["research-secret"]),
    )
    client = TestClient(create_app(kb_root=kb_root))

    categories = client.get("/api/categories").json()
    browse = client.get("/api/browse", params={"module": "decoder"}).json()

    assert categories["tags"] == ["published-tag"]
    assert "pending-secret" not in categories["tags"]
    assert "research-secret" not in categories["tags"]
    assert [item["id"] for item in browse["entries"]] == ["KB-2026-0001"]


def test_http_surface_is_get_only_and_search_params_are_validated(tmp_path: Path) -> None:
    client = TestClient(create_app(kb_root=tmp_path / "kb"))

    assert client.post("/api/entries", json={}).status_code == 405
    assert client.put("/api/entries/KB-2026-0001", json={}).status_code == 405
    assert client.post("/api/research", json={}).status_code == 404
    assert client.post("/api/review/KB-2026-0001/approve", json={}).status_code == 404
    assert client.get("/api/entries", params={"status": "research"}).status_code == 422
    assert client.get("/api/entries", params={"min_support": "certain"}).status_code == 422
    assert client.get("/api/entries", params={"limit": "1000"}).status_code == 422


def test_build_scope_keeps_search_params_explicit() -> None:
    scope = build_scope(
        module="photo",
        entry_type="defect_case",
        error_code="-1",
        claim_type="observation",
        min_support="moderate",
        exclude_stale=True,
        status="published",
    )

    assert scope == {
        "module": "photo",
        "entry_type": "defect_case",
        "error_code": "-1",
        "claim_type": "observation",
        "min_support": "moderate",
        "exclude_stale": True,
        "status": "published",
    }


def test_get_entry_rejects_bad_published_markdown(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    bad_path = kb_root / "entries" / "KB-2026-0001.md"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("not frontmatter", encoding="utf-8")
    service = WebReadService(kb_root)

    with pytest.raises(WebApiError) as exc_info:
        service.get_entry("KB-2026-0001")

    assert exc_info.value.status_code == 404
    assert exc_info.value.field == "id"


def test_published_file_symlink_escape_is_rejected(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = kb_root / "entries" / "KB-2026-0001.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this filesystem: {exc}")

    with pytest.raises(WebApiError) as exc_info:
        WebReadService(kb_root).get_entry("KB-2026-0001")

    assert exc_info.value.field == "id"


def test_entries_directory_symlink_is_rejected(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    outside = tmp_path / "outside_entries"
    outside.mkdir()
    try:
        (kb_root / "entries").parent.mkdir(parents=True, exist_ok=True)
        (kb_root / "entries").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this filesystem: {exc}")

    with pytest.raises(WebApiError) as exc_info:
        WebReadService(kb_root).list_categories()

    assert exc_info.value.field == "kb_root"


def test_published_scan_errors_are_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_scan(*_args: object, **_kwargs: object) -> tuple[list[object], int]:
        raise ValueError("bad source")

    monkeypatch.setattr("web_api.service.read_valid_entries_from_source", fail_scan)

    with pytest.raises(WebApiError) as exc_info:
        WebReadService(tmp_path / "kb").list_categories()

    assert exc_info.value.code == "E_SCHEMA"
    assert exc_info.value.field == "kb_root"


def test_get_entry_source_error_response_does_not_leak_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    leaked_path = str(tmp_path / "secret" / "research")

    def fail_read(*_args: object, **_kwargs: object) -> object:
        raise ValueError(f"bad source {leaked_path}")

    monkeypatch.setattr("web_api.service.read_valid_entry_file", fail_read)
    client = TestClient(create_app(kb_root=kb_root))

    response = client.get("/api/entries/KB-2026-0001")

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "invalid entry source"
    assert leaked_path not in response.text


def test_categories_source_error_response_does_not_leak_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaked_path = str(tmp_path / "secret" / "entries")

    def fail_scan(*_args: object, **_kwargs: object) -> tuple[list[object], int]:
        raise ValueError(f"bad source {leaked_path}")

    monkeypatch.setattr("web_api.service.read_valid_entries_from_source", fail_scan)
    client = TestClient(create_app(kb_root=tmp_path / "kb"))

    response = client.get("/api/categories")

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "invalid published source"
    assert leaked_path not in response.text


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
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
