from fastapi.testclient import TestClient

from tests.conftest import FakeWordPress, load_fixture


def test_sections_excludes_nested_and_internal_categories(
    client: TestClient, fake_wp: FakeWordPress
):
    fake_wp.categories_by_page = {1: load_fixture("categories_page1.json")}

    response = client.get("/sections")

    assert response.status_code == 200
    names = [s["name"] for s in response.json()["sections"]]
    # Included: real top-level sections.
    assert "Sports" in names
    assert "Opinion" in names
    # Excluded: internal CMS ranking category (top-level but not a real
    # section) and a nested sub-category (not top-level).
    assert "weight-3" not in names
    assert "Men's Basketball" not in names


def test_sections_sorted_by_article_count_descending(
    client: TestClient, fake_wp: FakeWordPress
):
    fake_wp.categories_by_page = {1: load_fixture("categories_page1.json")}

    response = client.get("/sections")

    names = [s["name"] for s in response.json()["sections"]]
    assert names.index("Sports") < names.index("Opinion")
