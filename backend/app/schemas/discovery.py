"""Response schemas for current-affairs discovery."""

from pydantic import BaseModel


class DiscoveredArticle(BaseModel):
    """An article returned by the Google News RSS feed."""

    title: str
    publisher: str
    published_date: str
    url: str
