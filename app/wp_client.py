"""
Thin wrapper around the DTH WordPress REST API.

This module's only job is "talk to WordPress and hand back raw JSON (plus
pagination totals)". It knows nothing about our own API's response shape --
that translation happens in transform.py. Keeping that split means a change
to WordPress's data shape only touches this file + transform.py, and a
change to our own API's response shape never touches this file at all.
"""

import httpx

from .config import settings


class UpstreamError(Exception):
    """WordPress was unreachable, too slow, or returned a server error."""


class NotFoundError(Exception):
    """WordPress reported that the requested resource doesn't exist."""


async def _get(
    client: httpx.AsyncClient, path: str, params: dict | None = None
) -> httpx.Response:
    url = f"{settings.WP_API_BASE}{path}"
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise UpstreamError(
            "The Daily Tar Heel's website took too long to respond."
        ) from exc
    except httpx.RequestError as exc:
        raise UpstreamError(
            "Could not connect to The Daily Tar Heel's website."
        ) from exc

    if response.status_code == 404:
        raise NotFoundError("The requested article does not exist.")
    if response.status_code >= 500:
        raise UpstreamError("The Daily Tar Heel's website returned an error.")
    response.raise_for_status()
    return response


async def fetch_posts(
    client: httpx.AsyncClient,
    *,
    page: int,
    per_page: int,
    category_id: int | None = None,
    search: str | None = None,
) -> tuple[list[dict], int, int]:
    """Fetch a page of posts. Returns (posts, total_count, total_pages).

    `_embed=1` asks WordPress to inline the related objects a post links to
    (its categories/tags/author-style taxonomies and its featured image) in
    one response, instead of us having to make a separate request per post
    per related object -- the difference between ~1 request and ~30+
    requests for a page of 10 articles.
    """
    params: dict = {"page": page, "per_page": per_page, "_embed": "1"}
    if category_id is not None:
        params["categories"] = category_id
    if search:
        params["search"] = search

    response = await _get(client, "/posts", params)
    total = int(response.headers.get("X-WP-Total", "0"))
    total_pages = int(response.headers.get("X-WP-TotalPages", "0"))
    return response.json(), total, total_pages


async def fetch_post(client: httpx.AsyncClient, post_id: int) -> dict:
    response = await _get(client, f"/posts/{post_id}", {"_embed": "1"})
    return response.json()


async def _fetch_categories_page(
    client: httpx.AsyncClient, page: int, per_page: int = 100
) -> tuple[list[dict], int]:
    response = await _get(client, "/categories", {"page": page, "per_page": per_page})
    total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
    return response.json(), total_pages


async def fetch_top_level_sections(client: httpx.AsyncClient) -> list[dict]:
    """Fetch every top-level (non-nested) category.

    DTH has 300+ categories total -- most are narrow sub-topics (individual
    sports teams, one-off election years, etc.) nested under a handful of
    top-level ones (Sports, Opinion, University, ...). Those top-level
    categories are what a "section tab bar" in a news app actually wants, so
    we filter by `parent == 0` here rather than exposing the raw, much
    noisier full list.

    We also drop categories whose slug starts with "weight-": these are
    internal, invisible categories DTH's CMS uses to manually rank stories
    on their homepage. They carry no meaning for readers and would show up
    as a nonsense section called "weight-3" otherwise.

    WordPress caps `per_page` at 100, so this may take a few sequential
    requests to walk every page of categories. That cost is exactly why
    this result is cached for much longer than article data (see
    config.SECTIONS_CACHE_TTL_SECONDS).
    """
    page = 1
    collected: list[dict] = []
    while True:
        categories, total_pages = await _fetch_categories_page(client, page=page)
        collected.extend(
            c
            for c in categories
            if c.get("parent") == 0 and not c.get("slug", "").startswith("weight-")
        )
        if page >= total_pages:
            break
        page += 1
    collected.sort(key=lambda c: c.get("count", 0), reverse=True)
    return collected
