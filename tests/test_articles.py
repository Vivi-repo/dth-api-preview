"""
Route-level tests for /articles and /articles/{id}, using the fake
WordPress transport from conftest.py -- no real network calls happen.
"""

from fastapi.testclient import TestClient

from tests.conftest import FakeWordPress, load_fixture


def test_list_articles_returns_clean_shape(client: TestClient, fake_wp: FakeWordPress):
    fake_wp.posts = [load_fixture("post_with_byline.json")]
    fake_wp.posts_total = 1
    fake_wp.posts_total_pages = 1

    response = client.get("/articles")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["total"] == 1
    article = body["articles"][0]
    assert article["author"] == "Mary Stevens"
    assert article["section"] == "Faith Hedgepeth Trial"
    assert "<p>" not in article["excerpt"]
    # The summary shouldn't include full article content.
    assert "content_html" not in article


def test_list_articles_forwards_page_and_per_page(
    client: TestClient, fake_wp: FakeWordPress
):
    fake_wp.posts = []
    fake_wp.posts_total = 0
    fake_wp.posts_total_pages = 0

    response = client.get("/articles?page=3&per_page=5")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 3
    assert body["per_page"] == 5


def test_per_page_above_max_is_rejected(client: TestClient):
    response = client.get("/articles?per_page=500")
    assert response.status_code == 422


def test_get_single_article_includes_cleaned_content(
    client: TestClient, fake_wp: FakeWordPress
):
    post = load_fixture("post_weight_category_first.json")
    fake_wp.post_by_id[post["id"]] = post

    response = client.get(f"/articles/{post['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["author"] == "Olivia Wang"
    assert body["section"] == "Games"
    assert body["image_url"] is None
    assert "iframe" not in body["content_html"]


def test_get_article_not_found(client: TestClient, fake_wp: FakeWordPress):
    response = client.get("/articles/999999")
    assert response.status_code == 404
    assert "error" in response.json()


def test_articles_filtered_by_section(client: TestClient, fake_wp: FakeWordPress):
    fake_wp.posts = [load_fixture("post_with_byline.json")]
    fake_wp.posts_total = 1
    fake_wp.posts_total_pages = 1

    response = client.get("/articles?section=6951")

    assert response.status_code == 200
    assert len(response.json()["articles"]) == 1
    # Our `section` query param should be forwarded as WordPress's
    # `categories` filter param.
    assert fake_wp.last_posts_params["categories"] == "6951"
