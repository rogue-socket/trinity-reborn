"""Best-effort article extraction using trafilatura and newspaper4k."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx
import newspaper
import trafilatura
from googlenewsdecoder import gnewsdecoder

from app.schemas.extraction import ExtractedArticle

logger = logging.getLogger(__name__)

MINIMUM_BODY_LENGTH = 200
MAX_CONCURRENT_EXTRACTIONS = 5
ExtractionMethod = Literal["trafilatura", "newspaper4k"]


@dataclass(frozen=True, slots=True)
class _ExtractionContent:
    """Intermediate successful extraction content."""

    title: str
    publisher: str | None
    published_date: str | None
    body: str


class ExtractionService:
    """Extract clean article text and metadata from a bounded URL batch."""

    async def extract(self, urls: list[str]) -> list[ExtractedArticle]:
        """Extract every URL concurrently without letting one failure abort a batch."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)
        articles = await asyncio.gather(
            *(self._extract_with_semaphore(url, semaphore) for url in urls)
        )
        succeeded = sum(article.success for article in articles)
        logger.info(
            "Article extraction batch complete: total=%d succeeded=%d failed=%d",
            len(articles),
            succeeded,
            len(articles) - succeeded,
        )
        return articles

    async def _extract_with_semaphore(
        self, url: str, semaphore: asyncio.Semaphore
    ) -> ExtractedArticle:
        """Run a single blocking extraction while respecting the batch limit."""
        async with semaphore:
            return await asyncio.to_thread(self._extract_one, url)

    def _extract_one(self, url: str) -> ExtractedArticle:
        """Extract one URL with trafilatura first, then newspaper4k as fallback."""
        errors: list[str] = []
        extraction_url = url
        if self._is_google_news_url(url):
            try:
                extraction_url = self._decode_google_news_url(url)
            except Exception as error:
                error_message = f"Google News decode failed: {error}"
                logger.warning(
                    "Google News decode failed: url=%s error=%s", url, error_message
                )
                return ExtractedArticle(
                    url=url,
                    title="",
                    publisher=None,
                    published_date=None,
                    body="",
                    extraction_method="trafilatura",
                    success=False,
                    error=error_message,
                )
            logger.info("Google News decoded: url=%s final_url=%s", url, extraction_url)
        for method, extractor in (
            ("trafilatura", self._extract_with_trafilatura),
            ("newspaper4k", self._extract_with_newspaper),
        ):
            try:
                content = extractor(extraction_url)
                if len(content.body.strip()) < MINIMUM_BODY_LENGTH:
                    errors.append(
                        f"{method} returned fewer than {MINIMUM_BODY_LENGTH} characters"
                    )
                    continue
            except Exception as error:
                errors.append(f"{method} failed: {error}")
                continue

            logger.info("Article extraction succeeded: url=%s method=%s", url, method)
            return ExtractedArticle(
                url=url,
                title=content.title,
                publisher=content.publisher,
                published_date=content.published_date,
                body=content.body,
                extraction_method=method,
                success=True,
                error=None,
            )

        error_message = "; ".join(errors) or "No extractor returned usable text"
        logger.warning("Article extraction failed: url=%s error=%s", url, error_message)
        return ExtractedArticle(
            url=url,
            title="",
            publisher=None,
            published_date=None,
            body="",
            extraction_method="newspaper4k",
            success=False,
            error=error_message,
        )

    @staticmethod
    def _is_google_news_url(url: str) -> bool:
        """Return whether a URL is a Google News RSS article wrapper."""
        return url.startswith("https://news.google.com/rss/articles/")

    @staticmethod
    def _resolve_final_url(url: str) -> str:
        """Follow a non-Google short-link URL to its final destination."""
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.get(url)
            response.raise_for_status()

        final_url = str(response.url)
        return final_url

    @staticmethod
    def _decode_google_news_url(url: str) -> str:
        """Decode a Google News RSS article wrapper via Google's batchexecute flow."""
        result = gnewsdecoder(url)
        if result.get("status") is not True:
            raise ValueError(result.get("message", "decoder returned no URL"))
        decoded_url = result.get("decoded_url")
        if not isinstance(decoded_url, str) or not decoded_url:
            raise ValueError("decoder returned an empty publisher URL")
        return decoded_url

    @staticmethod
    def _extract_with_trafilatura(url: str) -> _ExtractionContent:
        """Fetch and extract content with trafilatura."""
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise ValueError("could not download URL")

        body = trafilatura.extract(downloaded, include_comments=False)
        if not body:
            raise ValueError("did not return article text")

        metadata = trafilatura.extract_metadata(downloaded)
        return _ExtractionContent(
            title=metadata.title or url,
            publisher=metadata.sitename,
            published_date=metadata.date,
            body=body,
        )

    @staticmethod
    def _extract_with_newspaper(url: str) -> _ExtractionContent:
        """Fetch and extract content with newspaper4k."""
        article = newspaper.Article(url)
        article.download()
        article.parse()
        if not article.text:
            raise ValueError("did not return article text")

        published_date = ExtractionService._format_published_date(article.publish_date)
        return _ExtractionContent(
            title=article.title or url,
            publisher=article.meta_site_name,
            published_date=published_date,
            body=article.text,
        )

    @staticmethod
    def _format_published_date(value: datetime | None) -> str | None:
        """Normalize newspaper4k's optional publication datetime."""
        return value.isoformat() if value is not None else None
