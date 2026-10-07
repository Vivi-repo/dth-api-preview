"""
Shared pytest fixtures.

The key idea: we never let tests make real network calls to
dailytarheel.com. Instead, `httpx.AsyncClient` is built with a
`MockTransport` -- a function that receives the outgoing request and
returns a canned `httpx.Response` directly, without touching a socket.
That fake client is then handed to the app in place of the real one via
FastAPI's dependency override mechanism (`app.dependency_overrides`), so
route code runs completely unmodified in tests.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_http_client

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FakeWordPress:
    """A tiny stand-in for the DTH WordPress REST API. Tests configure its
    `posts`, `post_by_id`, and `categories_by_page` attributes to control
    what each route returns."""

    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.posts_total = 0
        self.posts_total_pages = 0
        self.post_by_id: dict[int, dict] = {}
        self.categories_by_page: dict[int, list[dict]] = {1: []}
        self.raise_timeout = False
        self.raise_connect_error = False
        self.last_posts_params: dict | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.raise_timeout:
            raise httpx.TimeoutException("simulated timeout", request=request)
        if self.raise_connect_error:
            raise httpx.ConnectError("simulated connection failure", request=request)

        path = request.url.path
        params = dict(request.url.params)

        if path == "/wp-json/wp/v2/posts":
            self.last_posts_params = params
            return httpx.Response(
                200,
                json=self.posts,
                headers={
                    "X-WP-Total": str(self.posts_total),
                    "X-WP-TotalPages": str(self.posts_total_pages),
                },
            )

        if path.startswith("/wp-json/wp/v2/posts/"):
            post_id = int(path.rsplit("/", 1)[-1])
            post = self.post_by_id.get(post_id)
            if post is None:
                return httpx.Response(404, json={"code": "rest_post_invalid_id"})
            return httpx.Response(200, json=post)

        if path == "/wp-json/wp/v2/categories":
            page = int(params.get("page", "1"))
            total_pages = len(self.categories_by_page)
            return httpx.Response(
                200,
                json=self.categories_by_page.get(page, []),
                headers={"X-WP-TotalPages": str(total_pages)},
            )

        raise AssertionError(f"Unexpected request to {path}")


@pytest.fixture
def fake_wp() -> FakeWordPress:
    return FakeWordPress()


@pytest.fixture
def client(fake_wp: FakeWordPress):
    # Call through a lambda (not `fake_wp.handler` directly) so that a test
    # which replaces `fake_wp.handler` after this fixture runs (e.g. to wrap
    # it with a call counter) still takes effect.
    transport = httpx.MockTransport(lambda request: fake_wp.handler(request))
    fake_client = httpx.AsyncClient(transport=transport)

    app.dependency_overrides[get_http_client] = lambda: fake_client
    # Each test gets a fresh cache so earlier tests' responses can't leak in.
    from app import service

    service.cache._store.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
