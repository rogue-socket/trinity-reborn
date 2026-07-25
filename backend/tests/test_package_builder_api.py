"""Tests for the research-package API endpoint."""

from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_deduplication_service,
    get_package_builder_service,
)
from app.main import app
from app.schemas.deduplication import DeduplicatedArticle, DeduplicationGroup
from app.schemas.extraction import ExtractedArticle
from app.schemas.package import PackageMetadata, ResearchPackage


def test_build_package_endpoint_deduplicates_then_builds() -> None:
    extracted_article = ExtractedArticle(
        url="https://example.com/article",
        title="Article",
        publisher="Example News",
        published_date="2026-07-25",
        body="Article body",
        extraction_method="trafilatura",
        success=True,
        error=None,
    )
    representative = DeduplicatedArticle(
        url=extracted_article.url,
        title=extracted_article.title,
        publisher=extracted_article.publisher,
        published_date=extracted_article.published_date,
        body=extracted_article.body,
        duplicate_of=None,
    )

    class FakeDeduplicationService:
        def deduplicate(
            self, articles: list[ExtractedArticle]
        ) -> list[DeduplicationGroup]:
            assert articles == [extracted_article]
            return [DeduplicationGroup(representative=representative, duplicates=[])]

    class FakePackageBuilderService:
        async def build_full_package(
            self, topic_key: str, groups: list[DeduplicationGroup]
        ) -> ResearchPackage:
            assert topic_key == "india"
            assert groups[0].representative == representative
            return ResearchPackage(
                schema_version="1.0",
                package_id="package-001",
                topic_key=topic_key,
                metadata=PackageMetadata(
                    title=topic_key,
                    generated_at="2026-07-25T10:00:00Z",
                ),
                sources=[],
                articles=[],
                evidence=[],
                entities=[],
                events=[],
                claims=[],
            )

    async def override_deduplication() -> FakeDeduplicationService:
        return FakeDeduplicationService()

    async def override_package_builder() -> FakePackageBuilderService:
        return FakePackageBuilderService()

    app.dependency_overrides[get_deduplication_service] = override_deduplication
    app.dependency_overrides[get_package_builder_service] = override_package_builder
    try:
        response = TestClient(app).post(
            "/build-package",
            json={"topic_key": "india", "articles": [extracted_article.model_dump()]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["topic_key"] == "india"
