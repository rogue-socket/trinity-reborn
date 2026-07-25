"""Dependency providers for API routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.discovery import DiscoveryRepository
from app.services.discovery.service import GoogleNewsDiscoveryService
from app.services.discovery.workflow import DiscoveryWorkflow


async def get_discovery_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DiscoveryWorkflow:
    """Build a discovery workflow with request-scoped persistence."""
    return DiscoveryWorkflow(
        discovery_service=GoogleNewsDiscoveryService(),
        repository=DiscoveryRepository(session),
    )
