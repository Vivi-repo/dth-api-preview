"""
Pydantic models: the public shape of our API, independent of whatever
WordPress happens to return. FastAPI uses these to validate responses and
to generate the interactive docs at /docs.
"""

from pydantic import BaseModel


class Section(BaseModel):
    id: int
    name: str
    slug: str
    article_count: int


class SectionListResponse(BaseModel):
    sections: list[Section]


class ArticleSummary(BaseModel):
    id: int
    title: str
    author: str | None
    published_at: str
    section: str | None
    section_id: int | None
    excerpt: str
    image_url: str | None
    url: str


class ArticleDetail(ArticleSummary):
    content_html: str


class ArticleListResponse(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    articles: list[ArticleSummary]


class ErrorResponse(BaseModel):
    error: str
