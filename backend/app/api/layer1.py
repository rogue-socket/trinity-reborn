"""Layer 1 research endpoints hosted beside the Layer 2 graph service."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_session
from app.models import DiscoveredArticleRecord, DiscoveryRequest
from app.services.layer1 import (
    DeduplicationRequest,
    DeduplicationResponse,
    DiscoveryError,
    DiscoveredArticle,
    ExtractionRequest,
    ExtractionResponse,
    PackageBuildRequest,
    PackageValidationError,
    ResearchPackage,
    build_full_package,
    deduplicate,
    discover,
    extract,
    google_news_search_url,
)


router = APIRouter(tags=["layer-1-research"])
logger = logging.getLogger(__name__)


def _persist_discovery(
    session: Session,
    topic: str,
    limit: int,
    status_value: str,
    articles: list[DiscoveredArticle],
) -> None:
    """Persist discovery history without making a successful fetch unavailable."""
    try:
        request = DiscoveryRequest(
            topic_key=topic,
            source_url=google_news_search_url(topic),
            requested_limit=limit,
            status=status_value,
            completed_at=datetime.now(UTC),
        )
        session.add(request)
        session.flush()
        session.add_all(
            DiscoveredArticleRecord(
                discovery_request_id=request.id,
                title=article.title,
                publisher=article.publisher,
                published_date=article.published_date,
                url=article.url,
            )
            for article in articles
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Could not persist Layer 1 discovery for topic=%r", topic)


@router.get("/discover", response_model=list[DiscoveredArticle])
def discover_current_affairs(
    topic: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[DiscoveredArticle]:
    """Discover and persist Google News metadata for a Layer 1 query."""
    try:
        articles = discover(topic, limit)
    except DiscoveryError as error:
        _persist_discovery(session, topic, limit, "failed", [])
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google News RSS is unavailable") from error
    _persist_discovery(session, topic, limit, "completed", articles)
    return articles


@router.post("/extract", response_model=ExtractionResponse)
async def extract_articles(request: ExtractionRequest) -> ExtractionResponse:
    return ExtractionResponse(articles=await extract(request.urls))


@router.post("/deduplicate", response_model=DeduplicationResponse)
def deduplicate_articles(request: DeduplicationRequest) -> DeduplicationResponse:
    return DeduplicationResponse(groups=deduplicate(request.articles))


@router.post("/build-package", response_model=ResearchPackage)
async def build_research_package(request: PackageBuildRequest) -> ResearchPackage:
    """Build a self-contained package suitable for direct ``/ingestions`` delivery."""
    try:
        return await build_full_package(request)
    except PackageValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=error.report,
        ) from error
