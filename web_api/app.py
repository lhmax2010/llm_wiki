"""FastAPI app for the human Web API surface."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

_GOVERNED_API_PATH = Path(__file__).resolve().parents[1] / "governed-api"
if str(_GOVERNED_API_PATH) not in sys.path:
    sys.path.append(str(_GOVERNED_API_PATH))

from governed_api.roles import RolesConfig, load_roles_config  # noqa: E402
from governed_api.types import Middleware  # noqa: E402

from core.id_allocator import IDAllocator  # noqa: E402
from index import SearchService  # noqa: E402
from web_api.service import (  # noqa: E402
    ClaimTypeParam,
    EntryTypeParam,
    SortParam,
    SupportParam,
    WebApiError,
    WebEntryCreateRequest,
    WebEntryPatchRequest,
    WebReadService,
    WebReviewDecisionRequest,
    WebReviewService,
    WebWriteService,
    build_scope,
    write_status_code,
)  # noqa: E402


def create_app(
    *,
    repo_root: Path | None = None,
    kb_root: Path | None = None,
    roles_config: RolesConfig | None = None,
    id_allocator: IDAllocator | None = None,
    audit_path: Path | None = None,
    pipeline_steps: tuple[Middleware, ...] | None = None,
    search_service: SearchService | None = None,
) -> FastAPI:
    resolved_repo_root = repo_root or Path(os.environ.get("UNIFIED_KB_REPO_ROOT", "."))
    resolved_kb_root = kb_root or Path(os.environ.get("UNIFIED_KB_ROOT", "kb"))
    resolved_roles_config = roles_config or load_roles_config(
        Path(os.environ.get("UNIFIED_KB_ROLES", "config/roles.yaml"))
    )
    app = FastAPI(title="Unified KB Web API", version="0.1.0")
    app.state.web_read_service = WebReadService(
        kb_root=resolved_kb_root,
        search_service=search_service,
    )
    app.state.web_write_service = WebWriteService(
        repo_root=resolved_repo_root,
        kb_root=resolved_kb_root,
        roles_config=resolved_roles_config,
        id_allocator=id_allocator,
        audit_path=audit_path,
        pipeline_steps=pipeline_steps,
    )
    app.state.web_review_service = WebReviewService(
        repo_root=resolved_repo_root,
        kb_root=resolved_kb_root,
        roles_config=resolved_roles_config,
        audit_path=audit_path,
    )

    @app.exception_handler(WebApiError)
    async def web_api_error_handler(_request: object, exc: WebApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "field": exc.field, "message": exc.message}},
        )

    @app.get("/api/entries")
    def search_entries(
        service: Annotated[WebReadService, Depends(_service)],
        q: Annotated[str, Query(max_length=200)] = "",
        module: Annotated[str | None, Query(max_length=120)] = None,
        entry_type: EntryTypeParam | None = None,
        error_code: Annotated[str | None, Query(max_length=120)] = None,
        claim_type: ClaimTypeParam | None = None,
        min_support: SupportParam | None = None,
        exclude_stale: bool = False,
        status: Literal["published"] | None = None,
        expand_synonyms: bool = True,
        limit: Annotated[int, Query(ge=0, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        sort: SortParam = "score",
    ) -> dict[str, object]:
        scope = build_scope(
            module=module,
            entry_type=entry_type,
            error_code=error_code,
            claim_type=claim_type,
            min_support=min_support,
            exclude_stale=exclude_stale,
            status=status,
        )
        entries = service.search_entries(
            q,
            scope=scope,
            expand_synonyms=expand_synonyms,
            limit=limit + 1,
            offset=offset,
            sort=sort,
        )
        return {
            "entries": entries[:limit],
            "has_more": len(entries) > limit,
        }

    @app.get("/api/entries/{entry_id}")
    def get_entry(
        service: Annotated[WebReadService, Depends(_service)],
        entry_id: Annotated[str, PathParam(max_length=64)],
    ) -> dict[str, object]:
        return {"entry": service.get_entry(entry_id)}

    @app.get("/api/categories")
    def list_categories(
        service: Annotated[WebReadService, Depends(_service)],
    ) -> dict[str, list[str]]:
        return service.list_categories()

    @app.get("/api/browse")
    def browse(
        service: Annotated[WebReadService, Depends(_service)],
        module: Annotated[str, Query(min_length=1, max_length=120)],
        entry_type: EntryTypeParam | None = None,
    ) -> dict[str, object]:
        return service.browse(module=module, entry_type=entry_type)

    @app.get("/api/graph")
    def graph(
        service: Annotated[WebReadService, Depends(_service)],
    ) -> dict[str, object]:
        return service.graph()

    @app.post("/api/entries")
    def propose_entry(
        payload: WebEntryCreateRequest,
        service: Annotated[WebWriteService, Depends(_write_service)],
        user: Annotated[str, Depends(_write_user)],
        _write_guard: Annotated[None, Depends(_require_write_request)],
    ) -> JSONResponse:
        result = service.propose_entry_from_web(payload, user=user)
        return JSONResponse(
            status_code=write_status_code(result, success_status=201),
            content=result,
        )

    @app.patch("/api/entries/{entry_id}")
    def propose_update(
        payload: WebEntryPatchRequest,
        service: Annotated[WebWriteService, Depends(_write_service)],
        user: Annotated[str, Depends(_write_user)],
        _write_guard: Annotated[None, Depends(_require_write_request)],
        entry_id: Annotated[str, PathParam(max_length=64)],
    ) -> JSONResponse:
        result = service.propose_update_from_web(entry_id, payload, user=user)
        return JSONResponse(
            status_code=write_status_code(result),
            content=result,
        )

    @app.get("/api/review/queue")
    def review_queue(
        service: Annotated[WebReviewService, Depends(_review_service)],
        user: Annotated[str, Depends(_write_user)],
    ) -> dict[str, object]:
        return service.review_queue_for_web(user=user)

    @app.get("/api/review/{entry_id}")
    def review_detail(
        service: Annotated[WebReviewService, Depends(_review_service)],
        user: Annotated[str, Depends(_write_user)],
        entry_id: Annotated[str, PathParam(max_length=64)],
    ) -> dict[str, object]:
        return service.review_detail_for_web(entry_id, user=user)

    @app.post("/api/review/{entry_id}/approve")
    def approve_review_item(
        payload: WebReviewDecisionRequest,
        service: Annotated[WebReviewService, Depends(_review_service)],
        user: Annotated[str, Depends(_write_user)],
        _write_guard: Annotated[None, Depends(_require_write_request)],
        entry_id: Annotated[str, PathParam(max_length=64)],
    ) -> JSONResponse:
        result = service.approve_from_web(entry_id, payload, user=user)
        return JSONResponse(status_code=write_status_code(result), content=result)

    @app.post("/api/review/{entry_id}/reject")
    def reject_review_item(
        payload: WebReviewDecisionRequest,
        service: Annotated[WebReviewService, Depends(_review_service)],
        user: Annotated[str, Depends(_write_user)],
        _write_guard: Annotated[None, Depends(_require_write_request)],
        entry_id: Annotated[str, PathParam(max_length=64)],
    ) -> JSONResponse:
        result = service.reject_from_web(entry_id, payload, user=user)
        return JSONResponse(status_code=write_status_code(result), content=result)

    return app


def _service(request: Request) -> WebReadService:
    service = request.app.state.web_read_service
    if not isinstance(service, WebReadService):
        raise RuntimeError("web read service is not configured")
    return service


def _write_service(request: Request) -> WebWriteService:
    service = request.app.state.web_write_service
    if not isinstance(service, WebWriteService):
        raise RuntimeError("web write service is not configured")
    return service


def _review_service(request: Request) -> WebReviewService:
    service = request.app.state.web_review_service
    if not isinstance(service, WebReviewService):
        raise RuntimeError("web review service is not configured")
    return service


def _write_user(x_kb_user: Annotated[str | None, Header()] = None) -> str:
    # P8 V1 uses an intranet trust header, not real authentication. Unknown
    # users still fail closed in Phase 2 RBAC.
    if x_kb_user is None or not x_kb_user.strip():
        raise WebApiError(
            "E_PERM", "X-KB-User header is required for writes", "headers.x-kb-user", 403
        )
    return x_kb_user.strip()


def _require_write_request(
    request: Request,
    x_kb_write_intent: Annotated[str | None, Header()] = None,
) -> None:
    if x_kb_write_intent != "web-edit":
        raise WebApiError(
            "E_PERM",
            "X-KB-Write-Intent: web-edit header is required for writes",
            "headers.x-kb-write-intent",
            403,
        )
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise WebApiError(
            "E_SCHEMA",
            "write requests require application/json",
            "headers.content-type",
            415,
        )


app = create_app()
