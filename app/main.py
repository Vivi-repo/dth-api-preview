"""
FastAPI application: route definitions and wiring. Business logic lives in
service.py; this file's job is just HTTP concerns -- parsing query params,
picking status codes, returning responses.
"""

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import service
from .config import settings
from .models import ArticleDetail, ArticleListResponse, SectionListResponse
from .wp_client import NotFoundError, UpstreamError

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared httpx client for the whole app's lifetime, so outgoing
    # requests reuse connections instead of renegotiating TLS/TCP on every
    # call -- the standard reason to build an httpx.AsyncClient once rather
    # than per-request.
    app.state.http_client = httpx.AsyncClient(
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT_SECONDS,
    )
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="DTH App Preview API", lifespan=lifespan)

# Wide open on purpose: every endpoint here is public, read-only GET data
# with no cookies/auth, meant to be called from any mobile client or, in
# the split-deployment setup (static preview on Vercel, this API on
# Render), from a browser on a different origin. There's no credential or
# per-user state here that a restrictive origin list would be protecting.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_http_client(request: Request) -> httpx.AsyncClient:
    """FastAPI dependency returning the shared httpx client. Routes depend
    on this function rather than reaching into app.state directly, so
    tests can override it with a mocked client via
    `app.dependency_overrides[get_http_client] = ...` without touching any
    route code."""
    return request.app.state.http_client


@app.exception_handler(UpstreamError)
async def handle_upstream_error(request: Request, exc: UpstreamError):
    # 503 Service Unavailable: *our* API is fine, but the data source it
    # depends on isn't -- a clear, honest status for the mobile app to
    # show a "try again shortly" message instead of crashing.
    return JSONResponse(status_code=503, content={"error": str(exc)})


@app.exception_handler(NotFoundError)
async def handle_not_found_error(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"error": str(exc)})


@app.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE),
    section: int | None = Query(
        None, description="Section (category) id to filter by"
    ),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    return await service.get_articles(
        client, page=page, per_page=per_page, category_id=section
    )


@app.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: int,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    return await service.get_article(client, article_id)


@app.get("/sections", response_model=SectionListResponse)
async def list_sections(client: httpx.AsyncClient = Depends(get_http_client)):
    return await service.get_sections(client)


@app.get("/search", response_model=ArticleListResponse)
async def search_articles(
    q: str = Query(..., min_length=1, description="Search keyword(s)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(settings.DEFAULT_PER_PAGE, ge=1, le=settings.MAX_PER_PAGE),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    return await service.get_articles(client, page=page, per_page=per_page, search=q)


# Registered last and mounted at "/" so it only catches requests that don't
# match one of the explicit API routes above (Starlette matches routes in
# registration order). `html=True` makes it serve static/index.html for "/"
# itself, the same way it would serve any other static site -- which is
# what lets this exact `static/` folder be deployed standalone (e.g. to
# Vercel) with no backend-specific routing.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
