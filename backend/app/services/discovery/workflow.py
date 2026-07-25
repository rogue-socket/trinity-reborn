"""Orchestration for RSS discovery and best-effort persistence."""

import logging
from typing import Protocol

from anyio import to_thread

from app.models.discovery import DiscoveryRequest
from app.schemas.discovery import DiscoveredArticle
from app.services.discovery.service import (
    GOOGLE_NEWS_RSS_URL,
    DiscoveryError,
)

logger = logging.getLogger(__name__)


class DiscoveryFeed(Protocol):
    """The RSS feed behavior required by the workflow."""

    def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
        """Fetch normalized article metadata."""


class DiscoveryPersistence(Protocol):
    """The persistence behavior required by the workflow."""

    async def create_request(self, source_url: str) -> DiscoveryRequest:
        """Create a pending request."""

    async def save_success(
        self,
        request: DiscoveryRequest,
        articles: list[DiscoveredArticle],
    ) -> None:
        """Persist successful discovery results."""

    async def mark_failed(self, request: DiscoveryRequest) -> None:
        """Persist failed request state."""


class DiscoveryWorkflow:
    """Run RSS discovery while recording the request and its results."""

    def __init__(
        self,
        discovery_service: DiscoveryFeed,
        repository: DiscoveryPersistence,
    ) -> None:
        self._discovery_service = discovery_service
        self._repository = repository

    async def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
        """Fetch RSS metadata and persist the request outcome when possible."""
        try:
            articles = await to_thread.run_sync(
                self._discovery_service.discover, topic, limit
            )
        except DiscoveryError:
            try:
                request = await self._repository.create_request(GOOGLE_NEWS_RSS_URL)
                await self._repository.mark_failed(request)
            except Exception as error:
                logger.exception(
                    "Could not persist failed discovery for topic=%r: %s", topic, error
                )
            raise

        try:
            request = await self._repository.create_request(GOOGLE_NEWS_RSS_URL)
            await self._repository.save_success(request, articles)
        except Exception as error:
            logger.exception(
                "Could not persist discovery results for topic=%r: %s", topic, error
            )

        return articles
