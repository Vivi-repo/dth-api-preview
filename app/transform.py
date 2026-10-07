"""
Turns raw WordPress post/category JSON into our own clean Pydantic models.

This is where all of DTH's WordPress-specific quirks are isolated, so that
nothing downstream (routes, the mobile app, the web preview) ever has to
know WordPress exists:

1. The standard WordPress "author" field/embed is disabled on this site
   (`/wp-json/wp/v2/users/*` returns 404). DTH instead tags each post with
   a custom taxonomy called "staff_name" holding the byline -- it shows up
   inside the embedded `wp:term` groups alongside categories and tags, not
   under the `author` key most WordPress examples assume. See
   `_extract_author`.
2. A post's categories include internal, non-editorial ones DTH's CMS adds
   for homepage ranking (slugs like "weight-3"). See `_extract_section`.
3. Article HTML comes straight out of DTH's editor (inline
   `style="font-weight:400"` spans, embedded widgets, etc.) and needs
   cleaning before it's fit for a mobile reading view.
"""

import html
import re

from bs4 import BeautifulSoup

from .models import ArticleDetail, ArticleSummary, Section


def _decode_entities(text: str) -> str:
    """WordPress sends titles/names with HTML entities (e.g. "City &amp;
    State"). This turns them back into plain text ("City & State")."""
    return html.unescape(text).strip()


def _strip_to_plain_text(raw_html: str) -> str:
    """Turn an HTML fragment into plain, readable text -- used for the
    article excerpt, which the mobile app shows as a plain string, not
    HTML."""
    text = BeautifulSoup(raw_html, "html.parser").get_text(separator=" ")
    # Collapse the runs of whitespace left behind by stripped tags.
    return re.sub(r"\s+", " ", text).strip()


# Tags that are pure noise for a reading view: scripts/styles are never
# content, and DTH embeds interactive widgets (e.g. the daily crossword) in
# a div that makes no sense outside their own website.
_TAGS_TO_REMOVE = ["script", "style", "iframe", "div.infographicwidget"]

# Attributes we keep. Everything else (style=, class=, id=, data-*, ...) is
# just editor/CMS cruft that a mobile app's renderer doesn't need and
# shouldn't have to parse.
_ATTRS_TO_KEEP = {"a": {"href"}, "img": {"src", "alt"}}


def _clean_content_html(raw_html: str) -> str:
    """Clean WordPress's raw editor HTML into a small, safe subset suitable
    for rendering in an app (e.g. a WKWebView or an HTML-to-AttributedString
    renderer), instead of full arbitrary markup."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for selector in _TAGS_TO_REMOVE:
        for tag in soup.select(selector):
            tag.decompose()

    for tag in soup.find_all(True):
        keep = _ATTRS_TO_KEEP.get(tag.name, set())
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in keep}
        # DTH's editor wraps huge amounts of plain text in
        # <span style="..."> purely for inline styling. The style is
        # already stripped above; the span itself adds nothing, so drop
        # the tag but keep its text/children.
        if tag.name == "span":
            tag.unwrap()

    return str(soup).strip()


def _embedded_term_group(post: dict, taxonomy: str) -> list[dict]:
    """WordPress embeds every taxonomy registered on a post (category,
    post_tag, staff_name, ...) as a list of term-groups under
    `_embedded["wp:term"]`, in the same order as the matching taxonomy
    links under `_links["wp:term"]`. There's no key telling you directly
    which group is which, so we line the two lists up by position to find
    the one we want.
    """
    links = post.get("_links", {}).get("wp:term", [])
    groups = post.get("_embedded", {}).get("wp:term", [])
    for link, group in zip(links, groups):
        if link.get("taxonomy") == taxonomy:
            return group
    return []


def _extract_author(post: dict) -> str | None:
    staff = _embedded_term_group(post, "staff_name")
    names = [_decode_entities(term["name"]) for term in staff if term.get("name")]
    return ", ".join(names) if names else None


def _extract_section(post: dict) -> tuple[int, str] | tuple[None, None]:
    categories = _embedded_term_group(post, "category")
    for term in categories:
        # Skip DTH's internal homepage-ranking categories (see wp_client's
        # fetch_top_level_sections docstring for the full explanation).
        if term.get("slug", "").startswith("weight-"):
            continue
        return term["id"], _decode_entities(term["name"])
    return None, None


def _extract_image_url(post: dict) -> str | None:
    media = post.get("_embedded", {}).get("wp:featuredmedia")
    if not media:
        return None
    first = media[0]
    return first.get("source_url")


def to_article_summary(post: dict) -> ArticleSummary:
    section_id, section_name = _extract_section(post)
    author = _extract_author(post)
    return ArticleSummary(
        id=post["id"],
        title=_decode_entities(post["title"]["rendered"]),
        author=author,
        published_at=post["date"],
        section=section_name,
        section_id=section_id,
        excerpt=_strip_to_plain_text(post["excerpt"]["rendered"]),
        image_url=_extract_image_url(post),
        url=post["link"],
    )


def to_article_detail(post: dict) -> ArticleDetail:
    summary = to_article_summary(post)
    return ArticleDetail(
        **summary.model_dump(),
        content_html=_clean_content_html(post["content"]["rendered"]),
    )


def to_section(category: dict) -> Section:
    return Section(
        id=category["id"],
        name=_decode_entities(category["name"]),
        slug=category["slug"],
        article_count=category.get("count", 0),
    )
