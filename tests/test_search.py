from fastapi.testclient import TestClient

from tests.conftest import FakeWordPress, load_fixture


def test_search_forwards_query_to_wordpress(client: TestClient, fake_wp: FakeWordPress):
    fake_wp.posts = [load_fixture("post_with_byline.json")]
    fake_wp.posts_total = 1
    fake_wp.posts_total_pages = 1

    response = client.get("/search?q=trial")

    assert response.status_code == 200
    assert len(response.json()["articles"]) == 1
    assert fake_wp.last_posts_params["search"] == "trial"


def test_search_requires_query_param(client: TestClient):
    response = client.get("/search")
    assert response.status_code == 422
