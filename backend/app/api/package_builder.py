"""HTTP endpoint for assembling Layer 1 research packages."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_deduplication_service,
    get_package_builder_service,
)
from app.schemas.deduplication import DeduplicationGroup
from app.schemas.package import PackageBuildRequest, ResearchPackage
from app.services.deduplication.service import DeduplicationService
from app.services.package_builder.service import PackageBuilderService

router = APIRouter(tags=["package-builder"])


@router.post("/build-package", response_model=ResearchPackage)
async def build_package(
    request: PackageBuildRequest,
    deduplication_service: Annotated[
        DeduplicationService, Depends(get_deduplication_service)
    ],
    package_builder_service: Annotated[
        PackageBuilderService, Depends(get_package_builder_service)
    ],
) -> ResearchPackage:
    """Deduplicate extracted articles and assemble a Layer 1 research package."""
    groups: list[DeduplicationGroup] = deduplication_service.deduplicate(
        request.articles
    )
    return await package_builder_service.build_full_package(request.topic_key, groups)
