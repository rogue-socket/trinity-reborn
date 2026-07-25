"""Dependency providers for API routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.discovery import DiscoveryRepository
from app.services.deduplication.service import DeduplicationService
from app.services.discovery.service import GoogleNewsDiscoveryService
from app.services.discovery.workflow import DiscoveryWorkflow
from app.services.extraction.service import ExtractionService
from app.services.package_builder.service import PackageBuilderService


async def get_extraction_service() -> ExtractionService:
    """Build the stateless article extraction service."""
    return ExtractionService()


async def get_deduplication_service() -> DeduplicationService:
    """Build the stateless article deduplication service."""
    return DeduplicationService()


async def get_package_builder_service() -> PackageBuilderService:
    """Build the package service without requiring Gemini configuration yet."""
    return PackageBuilderService()


async def get_discovery_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DiscoveryWorkflow:
    """Build a discovery workflow with request-scoped persistence."""
    return DiscoveryWorkflow(
        discovery_service=GoogleNewsDiscoveryService(),
        repository=DiscoveryRepository(session),
    )
