"""
Tests for the two cross-cutting concerns that aren't tied to one specific
endpoint: translating upstream failures into clean error responses, and the
in-memory cache avoiding repeat upstream calls.
"""

from fastapi.testclient import TestClient

from tests.conftest import FakeWordPress, load_fixture


def test_upstream_timeout_becomes_503(client: TestClient, fake_wp: FakeWordPress):
    fake_wp.raise_timeout = True

    response = client.get("/articles")

    assert response.status_code == 503
    assert "error" in response.json()


def test_upstream_connection_failure_becomes_503(
    client: TestClient, fake_wp: FakeWordPress
):
    fake_wp.raise_connect_error = True

    response = client.get("/sections")

    assert response.status_code == 503
    assert "error" in response.json()


def test_repeated_requests_hit_wordpress_only_once(
    client: TestClient, fake_wp: FakeWordPress
):
    """Two identical requests within the cache's TTL should only reach
    WordPress once -- the second is served entirely from cache."""
    fake_wp.posts = [load_fixture("post_with_byline.json")]
    fake_wp.posts_total = 1
    fake_wp.posts_total_pages = 1

    call_count = 0
    original_handler = fake_wp.handler

    def counting_handler(request):
        nonlocal call_count
        if request.url.path == "/wp-json/wp/v2/posts":
            call_count += 1
        return original_handler(request)

    fake_wp.handler = counting_handler

    first = client.get("/articles?page=1&per_page=10")
    second = client.get("/articles?page=1&per_page=10")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert call_count == 1
