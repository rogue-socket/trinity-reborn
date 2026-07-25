"""HTTP endpoint for article deduplication."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_deduplication_service
from app.schemas.deduplication import DeduplicationRequest, DeduplicationResponse
from app.services.deduplication.service import DeduplicationService

router = APIRouter(tags=["deduplication"])


@router.post("/deduplicate", response_model=DeduplicationResponse)
async def deduplicate_articles(
    request: DeduplicationRequest,
    service: Annotated[DeduplicationService, Depends(get_deduplication_service)],
) -> DeduplicationResponse:
    """Group a batch of extracted articles by underlying story."""
    if not request.articles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one article is required.",
        )

    return DeduplicationResponse(groups=service.deduplicate(request.articles))
