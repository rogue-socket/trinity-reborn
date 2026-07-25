"""Request and response schemas for article extraction."""

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedArticle(BaseModel):
    """Clean article content and metadata extracted from one URL."""

    url: str
    title: str
    publisher: str | None
    published_date: str | None
    body: str
    extraction_method: Literal["trafilatura", "newspaper4k"]
    success: bool
    error: str | None


class ExtractionRequest(BaseModel):
    """A bounded batch of article URLs to extract."""

    urls: list[str] = Field(max_length=50)


class ExtractionResponse(BaseModel):
    """The extracted result for every URL in a requested batch."""

    articles: list[ExtractedArticle]
