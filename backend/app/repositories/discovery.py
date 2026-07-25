"""Database access for discovery requests and their RSS results."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveryRequest, DiscoveryResult
from app.schemas.discovery import DiscoveredArticle


class DiscoveryRepository:
    """Persist discovery request state and normalized RSS results."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_request(self, source_url: str) -> DiscoveryRequest:
        """Create and flush a pending discovery request."""
        request = DiscoveryRequest(source_url=source_url)
        self._session.add(request)
        await self._session.flush()
        return request

    async def save_success(
        self,
        request: DiscoveryRequest,
        articles: list[DiscoveredArticle],
    ) -> None:
        """Store normalized feed items and mark a request as completed."""
        request.status = "completed"
        request.completed_at = datetime.now(UTC)
        self._session.add_all(
            [
                DiscoveryResult(
                    discovery_request_id=request.id,
                    headline=article.headline,
                    publisher=article.publisher,
                    published_date=article.published_date,
                    url=article.url,
                )
                for article in articles
            ]
        )
        await self._session.commit()

    async def mark_failed(self, request: DiscoveryRequest) -> None:
        """Record that a discovery request could not retrieve its feed."""
        request.status = "failed"
        request.completed_at = datetime.now(UTC)
        await self._session.commit()
