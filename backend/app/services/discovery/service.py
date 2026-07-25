"""Google News RSS discovery service.

This service only reads RSS metadata. It deliberately does not request article URLs.
"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import feedparser

from app.schemas.discovery import DiscoveredArticle

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"


class DiscoveryError(Exception):
    """Raised when the Google News feed cannot be retrieved or parsed."""


class GoogleNewsDiscoveryService:
    """Fetch and normalize the latest entries from Google News RSS."""

    def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
        """Return current Google News RSS entries without downloading articles."""
        feed = feedparser.parse(build_google_news_rss_url(topic))
        entries = feed.get("entries", [])

        if feed.get("bozo") and not entries:
            error = feed.get("bozo_exception", "unknown RSS parsing error")
            raise DiscoveryError(f"Unable to parse Google News RSS: {error}")

        return [
            self._to_article(entry)
            for entry in entries
            if entry.get("link")
        ][:limit]

    @staticmethod
    def _to_article(entry: Mapping[str, Any]) -> DiscoveredArticle:
        """Normalize one RSS entry into the API response format."""
        source = entry.get("source", {})
        publisher = source.get("title") if isinstance(source, Mapping) else None

        return DiscoveredArticle(
            title=entry.get("title", ""),
            publisher=publisher or entry.get("author", "Unknown"),
            published_date=entry.get("published", entry.get("updated", "")),
            url=entry["link"],
        )


def build_google_news_rss_url(topic: str) -> str:
    """Build the Google News RSS search URL for a requested topic."""
    query = urlencode({"q": topic, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{query}"
