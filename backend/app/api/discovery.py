"""HTTP endpoints for current-affairs discovery."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_discovery_workflow
from app.schemas.discovery import DiscoveredArticle
from app.services.discovery.service import DiscoveryError
from app.services.discovery.workflow import DiscoveryWorkflow

router = APIRouter(tags=["discovery"])


@router.get("/discover", response_model=list[DiscoveredArticle])
async def discover_current_affairs(
    workflow: Annotated[DiscoveryWorkflow, Depends(get_discovery_workflow)],
    topic: Annotated[str | None, Query(description="Topic to search for")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[DiscoveredArticle]:
    """Return and persist the latest Google News RSS metadata."""
    if topic is None or not topic.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A topic query parameter is required.",
        )

    try:
        return await workflow.discover(topic=topic, limit=limit)
    except DiscoveryError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google News RSS is currently unavailable.",
        ) from error
