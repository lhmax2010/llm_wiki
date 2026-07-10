from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from governed_api.roles import RolesConfig
from governed_api.types import MiddlewareContext, MiddlewareResult, ok

from core.id_allocator import IDAllocator
from core.models import Entry
from core.storage import read_entry, write_entry
from index import SearchService
from research.store import ResearchRecord, write_research_record
from tests.governed_api.helpers import entry_payload
from web_api.app import create_app
from web_api.service import WebApiError, WebReadService, build_scope

WRITE_HEADERS = {"X-KB-User": "alice", "X-KB-Write-Intent": "web-edit"}
REVIEW_HEADERS = {"X-KB-User": "reviewer", "X-KB-Write-Intent": "web-edit"}


@pytest.fixture
def roles_config() -> RolesConfig:
    return RolesConfig(
        roles={
            "reader": ["read_published"],
            "contributor": ["read_published", "propose_entry"],
            "light_reviewer": [
                "read_published",
                "review_light",
                "publish_entry",
                "deprecate_entry",
            ],
            "reviewer": [
                "read_published",
                "propose_entry",
                "review_light",
                "review_heavy",
                "publish_entry",
                "deprecate_entry",
            ],
            "admin": ["*"],
        },
        users={
            "alice": "contributor",
            "reader": "reader",
            "light": "light_reviewer",
            "reviewer": "reviewer",
            "admin": "admin",
        },
    )


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
    assert hidden.json()["has_more"] is False


def test_search_entries_reports_has_more_for_pagination(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    for number in range(1, 4):
        payload = entry_payload(entry_id=f"KB-2026-{number:04d}", trust_state="published")
        payload["title"] = f"Paginated case {number}"
        _write_payload(kb_root / "entries" / f"KB-2026-{number:04d}.md", payload)
    client = TestClient(create_app(kb_root=kb_root))

    first_page = client.get("/api/entries", params={"q": "Paginated", "limit": 2, "offset": 0})
    second_page = client.get("/api/entries", params={"q": "Paginated", "limit": 2, "offset": 2})

    assert first_page.status_code == 200
    assert len(first_page.json()["entries"]) == 2
    assert first_page.json()["has_more"] is True
    assert second_page.status_code == 200
    assert len(second_page.json()["entries"]) == 1
    assert second_page.json()["has_more"] is False


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


def test_graph_only_uses_published_entries_and_published_edges(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    source = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    source["title"] = "Graph source"
    source["related"] = [
        {"target": "KB-2026-0002", "type": "related", "origin": "human"},
        {"target": "KB-2026-0003", "type": "same_root_cause", "origin": "human"},
        {"target": "KB-2026-0004", "type": "related", "origin": "human"},
    ]
    target = entry_payload(entry_id="KB-2026-0002", trust_state="published")
    target["title"] = "Graph target"
    target["related"] = [{"target": "KB-2026-0001", "type": "related", "origin": "human"}]
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", source)
    _write_payload(kb_root / "entries" / "KB-2026-0002.md", target)
    _write_payload(
        kb_root / "staging" / "KB-2026-0003.md",
        entry_payload(entry_id="KB-2026-0003", trust_state="pending"),
    )
    _write_payload(
        kb_root / "deprecated" / "KB-2026-0004.md",
        entry_payload(entry_id="KB-2026-0004", trust_state="deprecated"),
    )
    _write_research(kb_root, "R-2026-0001", title="research graph secret")
    client = TestClient(create_app(kb_root=kb_root))

    response = client.get("/api/graph")

    assert response.status_code == 200
    graph = response.json()
    assert [node["id"] for node in graph["nodes"]] == ["KB-2026-0001", "KB-2026-0002"]
    assert graph["edges"] == [
        {
            "source": "KB-2026-0001",
            "target": "KB-2026-0002",
            "types": ["related"],
            "origins": ["human"],
            "notes": [],
            "bidirectional": True,
        }
    ]
    assert "KB-2026-0003" not in response.text
    assert "KB-2026-0004" not in response.text
    assert "research graph secret" not in response.text


def test_http_surface_is_get_only_and_search_params_are_validated(tmp_path: Path) -> None:
    client = TestClient(create_app(kb_root=tmp_path / "kb"))

    assert client.post("/api/entries", json={}).status_code == 403
    assert client.put("/api/entries/KB-2026-0001", json={}).status_code == 405
    assert client.post("/api/entries/KB-2026-0001/related", json={}).status_code == 404
    assert client.post("/api/research", json={}).status_code == 404
    assert client.put("/api/review/KB-2026-0001/approve", json={}).status_code == 405
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


def test_web_propose_entry_runs_all_pipeline_steps(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    calls: list[int] = []

    def step(number: int) -> Callable[[MiddlewareContext], MiddlewareResult]:
        def _step(context: MiddlewareContext) -> MiddlewareResult:
            calls.append(number)
            next_context = context.copy()
            if number == 6:
                next_context["allocated_id"] = "KB-2026-0001"
                next_context["target_dir"] = "staging"
                next_context["review_level"] = "heavy"
            return ok(next_context)

        return _step

    client = TestClient(
        create_app(
            repo_root=tmp_path,
            kb_root=tmp_path / "kb",
            roles_config=roles_config,
            pipeline_steps=(step(1), step(2), step(3), step(4), step(5), step(6), step(7)),
        )
    )

    response = client.post("/api/entries", json=_web_create_payload(), headers=WRITE_HEADERS)

    assert response.status_code == 201
    assert calls == [1, 2, 3, 4, 5, 6, 7]
    assert response.json()["proposed_id"] == "KB-2026-0001"
    assert response.json()["status"] == "pending"


def test_web_propose_entry_persists_to_staging_and_audit(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    client = TestClient(
        create_app(
            repo_root=tmp_path,
            kb_root=kb_root,
            roles_config=roles_config,
            id_allocator=IDAllocator(kb_root / "indexes" / "ids.sqlite"),
        )
    )

    response = client.post("/api/entries", json=_web_create_payload(), headers=WRITE_HEADERS)

    assert response.status_code == 201
    assert response.json()["ok"] is True
    assert response.json()["proposed_id"] == "KB-2026-0001"
    assert response.json()["status"] == "pending"
    assert response.json()["target_dir"] == "staging"
    assert (kb_root / "staging" / "KB-2026-0001.md").is_file()
    assert not (kb_root / "entries" / "KB-2026-0001.md").exists()
    assert (kb_root / "indexes" / "audit.jsonl").is_file()


def test_web_propose_entry_accepts_valid_related_through_pipeline(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))
    payload = _web_create_payload()
    payload["related"] = [{"target": "KB-2026-0001", "type": "related"}]

    response = client.post("/api/entries", json=payload, headers=WRITE_HEADERS)

    assert response.status_code == 201
    assert response.json()["ok"] is True
    staged = read_entry(kb_root / "staging" / f"{response.json()['proposed_id']}.md")
    assert staged.related[0].target == "KB-2026-0001"
    assert staged.related[0].origin == "human"


@pytest.mark.parametrize("target", ["R-2026-0001", "KB-2026-9999"])
def test_web_propose_entry_rejects_research_or_missing_related_targets(
    tmp_path: Path,
    roles_config: RolesConfig,
    target: str,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )
    payload = _web_create_payload()
    payload["related"] = [{"target": target, "type": "related"}]

    response = client.post("/api/entries", json=payload, headers=WRITE_HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_SCHEMA"
    assert "related[0].target" in response.json()["error"]["field"]
    assert not (tmp_path / "kb" / "staging").exists()


def test_web_patch_rejects_self_related_edge(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.patch(
        "/api/entries/KB-2026-0001",
        json={"related": [{"target": "KB-2026-0001", "type": "related"}]},
        headers=WRITE_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_SCHEMA"
    assert "related[0].target" in response.json()["error"]["field"]


def test_web_create_rebuilds_empty_allocator_before_issuing_id(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    client = TestClient(
        create_app(
            repo_root=tmp_path,
            kb_root=kb_root,
            roles_config=roles_config,
            id_allocator=IDAllocator(kb_root / "indexes" / "ids.sqlite"),
        )
    )

    response = client.post("/api/entries", json=_web_create_payload(), headers=WRITE_HEADERS)

    assert response.status_code == 201
    assert response.json()["proposed_id"] == "KB-2026-0002"
    assert (kb_root / "entries" / "KB-2026-0001.md").is_file()
    assert (kb_root / "staging" / "KB-2026-0002.md").is_file()
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()


def test_web_propose_update_persists_to_staging_and_keeps_published_entry(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.patch(
        "/api/entries/KB-2026-0001",
        json={"body": entry_payload(entry_id=None)["body"].replace("content.", "updated.")},
        headers=WRITE_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "pending"
    assert response.json()["review_level"] == "heavy"
    assert (kb_root / "staging" / "KB-2026-0001.md").is_file()
    assert (kb_root / "entries" / "KB-2026-0001.md").is_file()
    staged = Entry.model_validate(WebReadService(kb_root).get_entry("KB-2026-0001"))
    assert staged.trust_state == "published"


def test_web_writes_fail_closed_without_auth_or_write_intent(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )
    payload = _web_create_payload()

    missing_all = client.post("/api/entries", json=payload)
    missing_intent = client.post("/api/entries", json=payload, headers={"X-KB-User": "alice"})
    missing_user = client.post(
        "/api/entries",
        json=payload,
        headers={"X-KB-Write-Intent": "web-edit"},
    )

    assert missing_all.status_code == 403
    assert missing_intent.status_code == 403
    assert missing_user.status_code == 403


def test_web_write_rejects_form_encoded_content_type(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )

    response = client.post(
        "/api/entries",
        data={"title": "form post"},
        headers=WRITE_HEADERS,
    )

    assert response.status_code == 415
    assert response.json()["error"]["field"] == "headers.content-type"


def test_web_write_permissions_are_resolved_from_roles_config(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )
    payload = _web_create_payload()

    unknown = client.post(
        "/api/entries",
        json=payload,
        headers={"X-KB-User": "mallory", "X-KB-Write-Intent": "web-edit"},
    )
    spoofed_reader = client.post(
        "/api/entries",
        json=payload,
        headers={
            "X-KB-User": "reader",
            "X-KB-Role": "admin",
            "X-KB-Write-Intent": "web-edit",
        },
    )

    assert unknown.status_code == 403
    assert unknown.json()["error"]["code"] == "E_PERM"
    assert spoofed_reader.status_code == 403
    assert spoofed_reader.json()["error"]["field"] == "auth.permissions"


def test_web_create_rejects_self_declared_governance_fields(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )
    base = _web_create_payload()

    for field, value in {
        "id": "KB-2026-9999",
        "trust_state": "published",
        "author_type": "agent",
        "changed_fields": ["tags"],
        "target_dir": "entries",
        "role": "admin",
    }.items():
        response = client.post(
            "/api/entries",
            json={**base, field: value},
            headers=WRITE_HEADERS,
        )
        assert response.status_code == 422


def test_web_create_self_declared_claim_type_is_system_downgraded(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))
    payload = _web_create_payload()
    payload["credibility"] = {
        "claim_type": "fact",
        "support_strength": "strong",
        "evidence": [{"type": "human_note", "excerpt": "Observed by reviewer."}],
    }

    response = client.post("/api/entries", json=payload, headers=WRITE_HEADERS)

    assert response.status_code == 201
    assert response.json()["ok"] is True
    assert any(
        warning["code"] == "W_DOWNGRADE" for warning in response.json()["validation_warnings"]
    )
    staged = read_entry(kb_root / "staging" / f"{response.json()['proposed_id']}.md")
    assert staged.credibility.claim_type.value == "observation"


def test_web_patch_rejects_self_declared_diff_and_state_fields(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    for field, value in {
        "id": "KB-2026-9999",
        "trust_state": "published",
        "author_type": "agent",
        "changed_fields": ["tags"],
        "change_scopes": ["typo"],
        "review_level": "auto",
    }.items():
        response = client.patch(
            "/api/entries/KB-2026-0001",
            json={"tags": ["safe"], field: value},
            headers=WRITE_HEADERS,
        )
        assert response.status_code == 422


def test_web_patch_rejects_traversal_and_missing_entries(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )

    traversal = client.patch(
        "/api/entries/%2E%2E%2Fresearch%2FKB-2026-0001",
        json={"tags": ["safe"]},
        headers=WRITE_HEADERS,
    )
    missing = client.patch(
        "/api/entries/KB-2026-9999",
        json={"tags": ["safe"]},
        headers=WRITE_HEADERS,
    )

    assert traversal.status_code in {400, 404}
    assert missing.status_code == 404


def test_web_write_rejects_research_evidence(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    client = TestClient(
        create_app(repo_root=tmp_path, kb_root=tmp_path / "kb", roles_config=roles_config)
    )
    payload = _web_create_payload()
    payload["credibility"] = {
        "claim_type": "observation",
        "support_strength": "strong",
        "evidence": [{"type": "spec", "uri": "research:R-2026-0001", "version": "v1"}],
    }

    response = client.post("/api/entries", json=payload, headers=WRITE_HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_RESEARCH_AS_EVIDENCE"
    assert not (tmp_path / "kb" / "staging").exists()


def test_web_patch_refuses_to_overwrite_existing_pending_proposal(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="published"),
    )
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending"),
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.patch(
        "/api/entries/KB-2026-0001",
        json={"tags": ["safe"]},
        headers=WRITE_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "E_DUP"


def test_review_queue_requires_reviewer_permission(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending"),
    )
    _append_audit(kb_root, "KB-2026-0001", target_dir="staging", review_level="heavy")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    missing_user = client.get("/api/review/queue")
    contributor = client.get("/api/review/queue", headers={"X-KB-User": "alice"})
    reader = client.get("/api/review/queue", headers={"X-KB-User": "reader"})
    unknown = client.get("/api/review/queue", headers={"X-KB-User": "mallory"})
    reviewer = client.get("/api/review/queue", headers={"X-KB-User": "reviewer"})

    assert missing_user.status_code == 403
    assert contributor.status_code == 403
    assert reader.status_code == 403
    assert unknown.status_code == 403
    assert reviewer.status_code == 200
    assert reviewer.json()["backlog_count"] == 1
    assert reviewer.json()["items"][0]["entry_id"] == "KB-2026-0001"
    assert reviewer.json()["items"][0]["review_level"] == "heavy"


def test_web_review_detail_requires_reviewer_and_returns_full_pending_content(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "entries" / "KB-2026-0002.md",
        entry_payload(entry_id="KB-2026-0002", trust_state="published"),
    )
    payload = entry_payload(entry_id="KB-2026-0001", trust_state="pending")
    payload["title"] = "Pending detail note"
    payload["body"] = str(payload["body"]).replace("content.", "pending reviewer-only body.")
    payload["related"] = [{"target": "KB-2026-0002", "type": "related", "origin": "human"}]
    payload["source_refs"] = [
        {
            "type": "human_utterance",
            "role": "original_note",
            "text": "developer original note",
        }
    ]
    _write_payload(kb_root / "staging" / "KB-2026-0001.md", payload)
    _append_audit(kb_root, "KB-2026-0001", target_dir="staging", review_level="heavy")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    missing_user = client.get("/api/review/KB-2026-0001")
    contributor = client.get("/api/review/KB-2026-0001", headers={"X-KB-User": "alice"})
    reader = client.get("/api/review/KB-2026-0001", headers={"X-KB-User": "reader"})
    unknown = client.get("/api/review/KB-2026-0001", headers={"X-KB-User": "mallory"})
    reviewer = client.get("/api/review/KB-2026-0001", headers={"X-KB-User": "reviewer"})

    assert missing_user.status_code == 403
    assert contributor.status_code == 403
    assert reader.status_code == 403
    assert unknown.status_code == 403
    assert reviewer.status_code == 200
    detail = reviewer.json()
    assert detail["entry_id"] == "KB-2026-0001"
    assert detail["operation"] == "propose_entry"
    assert detail["review_level"] == "heavy"
    assert "pending reviewer-only body" in detail["proposal"]["body"]
    assert detail["proposal"]["source_refs"][0]["text"] == "developer original note"
    assert detail["proposal"]["related"][0]["target"] == "KB-2026-0002"
    assert detail["published"] is None
    assert detail["changed_fields"] == []
    assert detail["diff_available"] is False


def test_web_review_detail_update_diff_is_current_published_vs_staging(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    published = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    published["body"] = str(published["body"]).replace("content.", "current published v2.")
    published["updated"] = "2026-07-07T01:00:00Z"
    published["author"] = "bob"
    published["author_type"] = "agent"
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", published)
    proposal = entry_payload(entry_id="KB-2026-0001", trust_state="pending")
    proposal["body"] = str(proposal["body"]).replace("content.", "pending proposal body.")
    proposal["updated"] = "2026-07-07T02:00:00Z"
    proposal["author"] = "alice"
    proposal["author_type"] = "human"
    _write_payload(kb_root / "staging" / "KB-2026-0001.md", proposal)
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.get("/api/review/KB-2026-0001", headers={"X-KB-User": "reviewer"})

    assert response.status_code == 200
    detail = response.json()
    assert detail["operation"] == "propose_update"
    assert "current published v2" in detail["published"]["body"]
    assert "pending proposal body" in detail["proposal"]["body"]
    assert detail["diff_available"] is True
    assert detail["changed_fields"] == ["body"]
    assert "trust_state" not in detail["changed_fields"]
    assert "updated" not in detail["changed_fields"]
    assert "author" not in detail["changed_fields"]
    assert "author_type" not in detail["changed_fields"]


def test_web_review_detail_rejects_traversal_and_non_staging_sources(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "deprecated" / "KB-2026-0002.md",
        entry_payload(entry_id="KB-2026-0002", trust_state="deprecated"),
    )
    _write_payload(
        kb_root / "drafts" / "KB-2026-0003.md",
        entry_payload(entry_id="KB-2026-0003", trust_state="draft"),
    )
    _write_research(kb_root, "R-2026-0001", title="review detail research secret")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    traversal = client.get(
        "/api/review/%2E%2E%2Fresearch%2FR-2026-0001",
        headers={"X-KB-User": "reviewer"},
    )
    deprecated = client.get("/api/review/KB-2026-0002", headers={"X-KB-User": "reviewer"})
    draft = client.get("/api/review/KB-2026-0003", headers={"X-KB-User": "reviewer"})

    assert traversal.status_code in {400, 404}
    assert deprecated.status_code == 404
    assert draft.status_code == 404
    assert "review detail research secret" not in traversal.text
    assert "review detail research secret" not in deprecated.text
    assert "review detail research secret" not in draft.text


def test_web_review_approve_delegates_to_p5_service(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    service = SearchService(kb_root)
    service.rebuild_human_index()
    service.rebuild_agent_index()
    research = entry_payload(entry_id="KB-2026-0002", trust_state="research")
    research["title"] = "web-review-research-only-token"
    _write_payload(kb_root / "research" / "KB-2026-0002.md", research)
    proposal = entry_payload(entry_id="KB-2026-0001", trust_state="pending")
    proposal["title"] = "web-approve-refresh-token"
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        proposal,
    )
    _append_audit(kb_root, "KB-2026-0001", target_dir="staging", review_level="heavy")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.post(
        "/api/review/KB-2026-0001/approve",
        json={"note": "verified"},
        headers=REVIEW_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "published"
    assert response.json()["review_level"] == "heavy"
    assert (kb_root / "entries" / "KB-2026-0001.md").is_file()
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    published = read_entry(kb_root / "entries" / "KB-2026-0001.md")
    assert published.reviewer == "reviewer"
    visible = client.get("/api/entries", params={"q": "web-approve-refresh-token"})
    hidden = client.get("/api/entries", params={"q": "web-review-research-only-token"})
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["entries"]] == ["KB-2026-0001"]
    assert hidden.status_code == 200
    assert hidden.json()["entries"] == []
    assert [item["id"] for item in service.search_agent("web-approve-refresh-token")] == [
        "KB-2026-0001"
    ]
    audit = _last_audit(kb_root)
    assert audit["operation"] == "review_approve"
    assert audit["reviewer"] == "reviewer"
    assert audit["note"] == "verified"


def test_web_review_reject_delegates_to_p5_service(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending"),
    )
    _append_audit(kb_root, "KB-2026-0001", target_dir="staging", review_level="light")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.post(
        "/api/review/KB-2026-0001/reject",
        json={"note": "duplicate"},
        headers={"X-KB-User": "light", "X-KB-Write-Intent": "web-edit"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "deprecated"
    assert response.json()["review_level"] == "light"
    assert (kb_root / "deprecated" / "KB-2026-0001.md").is_file()
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    audit = _last_audit(kb_root)
    assert audit["operation"] == "review_reject"
    assert audit["reviewer"] == "light"
    assert audit["note"] == "duplicate"


def test_web_review_approve_republishes_update_proposal(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    original = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", original)
    updated_body = entry_payload(entry_id=None)["body"].replace("content.", "republished.")
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending", body=updated_body),
    )
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers=REVIEW_HEADERS,
    )

    assert response.status_code == 200
    republished = read_entry(kb_root / "entries" / "KB-2026-0001.md")
    assert republished.body == updated_body
    assert _last_audit(kb_root)["operation"] == "review_republish"


def test_web_review_reject_discards_update_proposal_without_deprecating_published(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    original = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", original)
    updated_body = entry_payload(entry_id=None)["body"].replace("content.", "rejected update.")
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending", body=updated_body),
    )
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    response = client.post(
        "/api/review/KB-2026-0001/reject",
        json={},
        headers=REVIEW_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "published"
    assert "review entry is not available" not in response.text
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").body == original["body"]
    assert not (kb_root / "staging" / "KB-2026-0001.md").exists()
    assert not (kb_root / "deprecated" / "KB-2026-0001.md").exists()
    assert _last_audit(kb_root)["operation"] == "review_reject_update"


def test_web_review_preserves_p5_terminal_and_audit_rollback_rules(
    tmp_path: Path,
    roles_config: RolesConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kb_root = tmp_path / "kb"
    existing = entry_payload(entry_id="KB-2026-0001", trust_state="published")
    _write_payload(kb_root / "entries" / "KB-2026-0001.md", existing)
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending"),
    )
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_entry",
    )
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    duplicate = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers=REVIEW_HEADERS,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "E_DUP"
    assert duplicate.json()["error"]["message"] == "review entry is not available"
    assert str(kb_root) not in duplicate.text
    assert "terminal entry already exists" not in duplicate.text
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").updated == existing["updated"]

    (kb_root / "staging" / "KB-2026-0001.md").unlink()
    updated_body = entry_payload(entry_id=None)["body"].replace("content.", "republished.")
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending", body=updated_body),
    )
    _append_audit(
        kb_root,
        "KB-2026-0001",
        target_dir="staging",
        review_level="heavy",
        operation="propose_update",
    )

    leaked_audit_path = str(tmp_path / "secret" / "audit.jsonl")

    def fail_append(*args: object, **kwargs: object) -> None:
        raise OSError(f"audit blocked at {leaked_audit_path}")

    monkeypatch.setattr("review.service.append_audit_record", fail_append)
    rollback = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers=REVIEW_HEADERS,
    )

    assert rollback.status_code == 400
    assert rollback.json()["error"]["field"] == "audit_path"
    assert rollback.json()["error"]["message"] == "review audit operation failed"
    assert leaked_audit_path not in rollback.text
    assert "secret" not in rollback.text
    assert read_entry(kb_root / "entries" / "KB-2026-0001.md").body == str(existing["body"])
    assert (kb_root / "staging" / "KB-2026-0001.md").exists()


def test_web_review_warning_response_does_not_leak_cleanup_path(
    tmp_path: Path,
    roles_config: RolesConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending"),
    )
    _append_audit(kb_root, "KB-2026-0001", target_dir="staging", review_level="heavy")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))
    original_unlink = Path.unlink
    leaked_source_path = str(kb_root / "staging" / "KB-2026-0001.md")

    def fail_staging_cleanup(self: Path, missing_ok: bool = False) -> None:
        if self.name == "KB-2026-0001.md" and self.parent.name == "staging":
            raise OSError(f"cleanup blocked for {leaked_source_path}")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_staging_cleanup)

    response = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers=REVIEW_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["warning"]["field"] == "staging_residue"
    assert response.json()["warning"]["message"] == "review source cleanup failed"
    assert leaked_source_path not in response.text
    assert str(kb_root) not in response.text


def test_web_review_permissions_and_trust_boundary_attacks(
    tmp_path: Path,
    roles_config: RolesConfig,
) -> None:
    kb_root = tmp_path / "kb"
    _write_payload(
        kb_root / "staging" / "KB-2026-0001.md",
        entry_payload(entry_id="KB-2026-0001", trust_state="pending"),
    )
    _append_audit(kb_root, "KB-2026-0001", target_dir="staging", review_level="heavy")
    client = TestClient(create_app(repo_root=tmp_path, kb_root=kb_root, roles_config=roles_config))

    contributor = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers=WRITE_HEADERS,
    )
    spoofed_role = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers={**WRITE_HEADERS, "X-KB-Role": "admin"},
    )
    missing_intent = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers={"X-KB-User": "reviewer"},
    )
    form_encoded = client.post(
        "/api/review/KB-2026-0001/approve",
        data={"note": "form"},
        headers=REVIEW_HEADERS,
    )
    injected = client.post(
        "/api/review/KB-2026-0001/approve",
        json={"note": "ok", "reviewer": "admin", "trust_state": "published"},
        headers=REVIEW_HEADERS,
    )
    traversal = client.post(
        "/api/review/%2E%2E%2Fresearch%2FKB-2026-0001/approve",
        json={},
        headers=REVIEW_HEADERS,
    )
    lock_dir = kb_root / "indexes" / "review_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "KB-2026-0001.lock").write_text("already running\n", encoding="utf-8")
    locked = client.post(
        "/api/review/KB-2026-0001/approve",
        json={},
        headers=REVIEW_HEADERS,
    )

    assert contributor.status_code == 403
    assert contributor.json()["error"]["field"] == "auth.permissions"
    assert spoofed_role.status_code == 403
    assert missing_intent.status_code == 403
    assert form_encoded.status_code == 415
    assert injected.status_code == 422
    assert traversal.status_code in {400, 404}
    assert locked.status_code == 409
    assert not (kb_root / "entries" / "KB-2026-0001.md").exists()


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


def _web_create_payload() -> dict[str, Any]:
    payload = entry_payload(entry_id=None, trust_state="pending")
    for field in ("schema_version", "trust_state", "author_type", "created", "updated"):
        payload.pop(field, None)
    return payload


def _append_audit(
    kb_root: Path,
    entry_id: str,
    *,
    target_dir: str,
    review_level: str,
    operation: str = "propose_entry",
) -> None:
    audit_path = kb_root / "indexes" / "audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, object] = {
        "timestamp": "2026-06-17T00:00:00+00:00",
        "user": "alice",
        "role": "contributor",
        "operation": operation,
        "entry_id": entry_id,
        "target_dir": target_dir,
        "path": f"{target_dir}/{entry_id}.md",
        "review_level": review_level,
    }
    with audit_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _last_audit(kb_root: Path) -> dict[str, object]:
    lines = (kb_root / "indexes" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    value = json.loads(lines[-1])
    assert isinstance(value, dict)
    return value
