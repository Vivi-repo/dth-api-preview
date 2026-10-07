"""
The layer between HTTP routes and the WordPress client: combines caching
+ fetching + transforming into the functions main.py calls directly. Routes
stay thin (parse request -> call a service function -> return it); all the
"how do we get this data efficiently" logic lives here instead.
"""

import httpx

from . import transform, wp_client
from .cache import TTLCache
from .config import settings
from .models import ArticleDetail, ArticleListResponse, SectionListResponse

# A single cache instance shared by every request this process handles.
cache = TTLCache()


async def get_articles(
    client: httpx.AsyncClient,
    *,
    page: int,
    per_page: int,
    category_id: int | None = None,
    search: str | None = None,
) -> ArticleListResponse:
    cache_key = f"articles:page={page}:per_page={per_page}:category={category_id}:search={search}"

    async def fetch() -> ArticleListResponse:
        posts, total, total_pages = await wp_client.fetch_posts(
            client,
            page=page,
            per_page=per_page,
            category_id=category_id,
            search=search,
        )
        return ArticleListResponse(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            articles=[transform.to_article_summary(post) for post in posts],
        )

    return await cache.get_or_fetch(
        cache_key, settings.ARTICLES_CACHE_TTL_SECONDS, fetch
    )


async def get_article(client: httpx.AsyncClient, article_id: int) -> ArticleDetail:
    cache_key = f"article:{article_id}"

    async def fetch() -> ArticleDetail:
        post = await wp_client.fetch_post(client, article_id)
        return transform.to_article_detail(post)

    return await cache.get_or_fetch(
        cache_key, settings.ARTICLES_CACHE_TTL_SECONDS, fetch
    )


async def get_sections(client: httpx.AsyncClient) -> SectionListResponse:
    cache_key = "sections"

    async def fetch() -> SectionListResponse:
        categories = await wp_client.fetch_top_level_sections(client)
        return SectionListResponse(
            sections=[transform.to_section(c) for c in categories]
        )

    return await cache.get_or_fetch(
        cache_key, settings.SECTIONS_CACHE_TTL_SECONDS, fetch
    )
