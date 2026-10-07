"""
Unit tests for the WordPress -> our-API translation logic in transform.py.

These don't go through HTTP at all -- they feed fixture JSON (shaped exactly
like what DTH's WordPress returns) straight into the transform functions.
This is where the trickiest, least-obvious behavior lives (the disabled
author endpoint workaround, filtering out internal "weight-*" categories,
cleaning editor HTML), so it gets the most direct test coverage.
"""

from app import transform
from tests.conftest import load_fixture


def test_author_comes_from_staff_name_taxonomy_not_author_field():
    post = load_fixture("post_with_byline.json")
    article = transform.to_article_summary(post)
    assert article.author == "Mary Stevens"


def test_section_skips_internal_weight_categories():
    post = load_fixture("post_with_byline.json")
    article = transform.to_article_summary(post)
    # "weight-3" is present in the post's categories but must never be
    # chosen as the display section.
    assert article.section == "Faith Hedgepeth Trial"
    assert article.section_id == 20120


def test_section_skips_weight_category_even_when_listed_first():
    post = load_fixture("post_weight_category_first.json")
    article = transform.to_article_summary(post)
    assert article.section == "Games"
    assert article.section_id == 7231


def test_excerpt_html_is_stripped_to_plain_text():
    post = load_fixture("post_with_byline.json")
    article = transform.to_article_summary(post)
    assert "<p>" not in article.excerpt
    assert article.excerpt == (
        "The defense and prosecution have selected three of the four "
        "required alternate jurors."
    )


def test_missing_featured_media_gives_none_image_url():
    post = load_fixture("post_weight_category_first.json")
    article = transform.to_article_summary(post)
    assert article.image_url is None


def test_present_featured_media_gives_source_url():
    post = load_fixture("post_with_byline.json")
    article = transform.to_article_summary(post)
    assert article.image_url == (
        "https://dailytarheel.com/wp-content/uploads/2026/09/courthouse.jpg"
    )


def test_content_html_strips_scripts_and_inline_styles():
    post = load_fixture("post_with_byline.json")
    detail = transform.to_article_detail(post)
    assert "<script>" not in detail.content_html
    assert "style=" not in detail.content_html
    assert "The trial continued Tuesday." in detail.content_html


def test_content_html_removes_embedded_widgets():
    post = load_fixture("post_weight_category_first.json")
    detail = transform.to_article_detail(post)
    assert "iframe" not in detail.content_html
    assert "infographicwidget" not in detail.content_html
