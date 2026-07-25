"""Response schemas for article deduplication."""

from pydantic import BaseModel

from app.schemas.extraction import ExtractedArticle


class DeduplicationRequest(BaseModel):
    """Articles to evaluate for duplicate stories."""

    articles: list[ExtractedArticle]


class DeduplicatedArticle(BaseModel):
    """An extracted article annotated with its representative, when duplicated."""

    url: str
    title: str
    publisher: str | None
    published_date: str | None
    body: str
    duplicate_of: str | None


class DeduplicationGroup(BaseModel):
    """A representative article and the articles judged to duplicate it."""

    representative: DeduplicatedArticle
    duplicates: list[DeduplicatedArticle]


class DeduplicationResponse(BaseModel):
    """Deduplication groups returned for a batch of extracted articles."""

    groups: list[DeduplicationGroup]
