"""FastAPI app for Phase 7a read-only Web access."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

_GOVERNED_API_PATH = Path(__file__).resolve().parents[1] / "governed-api"
if str(_GOVERNED_API_PATH) not in sys.path:
    sys.path.append(str(_GOVERNED_API_PATH))

from index import SearchService  # noqa: E402
from web_api.service import (  # noqa: E402
    ClaimTypeParam,
    EntryTypeParam,
    SortParam,
    SupportParam,
    WebApiError,
    WebReadService,
    build_scope,
)  # noqa: E402


def create_app(
    *,
    kb_root: Path | None = None,
    search_service: SearchService | None = None,
) -> FastAPI:
    resolved_kb_root = kb_root or Path(os.environ.get("UNIFIED_KB_ROOT", "kb"))
    app = FastAPI(title="Unified KB Readonly API", version="0.1.0")
    app.state.web_read_service = WebReadService(
        kb_root=resolved_kb_root,
        search_service=search_service,
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
        return {
            "entries": service.search_entries(
                q,
                scope=scope,
                expand_synonyms=expand_synonyms,
                limit=limit,
                offset=offset,
                sort=sort,
            )
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

    return app


def _service(request: Request) -> WebReadService:
    service = request.app.state.web_read_service
    if not isinstance(service, WebReadService):
        raise RuntimeError("web read service is not configured")
    return service


app = create_app()
