"""HTTP endpoint for best-effort article extraction."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_extraction_service
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.extraction.service import ExtractionService

router = APIRouter(tags=["extraction"])


@router.post("/extract", response_model=ExtractionResponse)
async def extract_articles(
    request: ExtractionRequest,
    service: Annotated[ExtractionService, Depends(get_extraction_service)],
) -> ExtractionResponse:
    """Extract article text and metadata without persisting results."""
    if not request.urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one URL is required.",
        )

    return ExtractionResponse(articles=await service.extract(request.urls))
