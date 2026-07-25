"""Response schemas for current-affairs discovery."""

from pydantic import BaseModel


class DiscoveredArticle(BaseModel):
    """An article headline returned by the Google News RSS feed."""

    headline: str
    publisher: str
    published_date: str
    url: str
