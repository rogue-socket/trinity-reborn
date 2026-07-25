"""Tests for deterministic Layer 1 research-package assembly."""

import asyncio
from hashlib import sha256
from uuid import UUID

from app.schemas.deduplication import DeduplicatedArticle, DeduplicationGroup
from app.schemas.package import Entity
from app.services.package_builder.llm_extraction import ExtractionResult
from app.services.package_builder.service import PackageBuilderService


def _article(
    *,
    url: str,
    publisher: str,
    published_date: str,
    body: str,
) -> DeduplicatedArticle:
    """Build a representative or duplicate article for package-builder tests."""
    return DeduplicatedArticle(
        url=url,
        title="Example article",
        publisher=publisher,
        published_date=published_date,
        body=body,
        duplicate_of=None,
    )


def test_build_base_package_creates_sources_articles_and_fingerprints() -> None:
    first = _article(
        url="https://example.com/first",
        publisher="Example News",
        published_date="2026-07-25T10:00:00Z",
        body="First representative article body.",
    )
    duplicate = _article(
        url="https://duplicate.example/first",
        publisher="Duplicate News",
        published_date="2026-07-25T10:05:00Z",
        body="Duplicate article body.",
    )
    second = _article(
        url="https://example.com/second",
        publisher="Example News",
        published_date="2026-07-25T11:00:00Z",
        body="Second representative article body.",
    )
    groups = [
        DeduplicationGroup(representative=first, duplicates=[duplicate]),
        DeduplicationGroup(representative=second, duplicates=[]),
    ]

    package = PackageBuilderService().build_base_package("india-protests", groups)

    assert package.schema_version == "1.0"
    assert UUID(package.package_id).version == 4
    assert package.topic_key == "india-protests"
    assert package.metadata.title == "india-protests"
    assert package.metadata.generated_at.endswith("+00:00")
    assert [source.source_id for source in package.sources] == ["src_001"]
    assert [source.publisher for source in package.sources] == ["Example News"]
    assert [article.article_id for article in package.articles] == [
        "art_001",
        "art_002",
    ]
    assert [article.source_id for article in package.articles] == ["src_001", "src_001"]
    assert [article.content for article in package.articles] == [
        first.body,
        second.body,
    ]
    expected_fingerprint = sha256(
        "\n".join(
            [first.url, first.publisher or "", first.published_date or "", first.body]
        ).encode("utf-8")
    ).hexdigest()
    assert package.articles[0].content_hash == expected_fingerprint
    assert package.evidence == []
    assert package.entities == []
    assert package.events == []
    assert package.claims == []


def test_build_full_package_merges_extraction_results() -> None:
    representative = _article(
        url="https://example.com/article",
        publisher="Example News",
        published_date="2026-07-25T10:00:00Z",
        body="Alice spoke at the meeting.",
    )

    class FakeInfoExtractionService:
        async def extract(self, articles: list[object]) -> ExtractionResult:
            assert len(articles) == 1
            return ExtractionResult(
                entities=[
                    Entity(
                        entity_id="ent_001",
                        label="Alice",
                        type="person",
                        aliases=[],
                        evidence_ids=[],
                    )
                ],
                events=[],
                claims=[],
                evidence=[],
                relationships=[],
            )

    service = PackageBuilderService(FakeInfoExtractionService())
    package = asyncio.run(
        service.build_full_package(
            "india", [DeduplicationGroup(representative=representative, duplicates=[])]
        )
    )

    assert [entity.label for entity in package.entities] == ["Alice"]


def test_build_full_package_returns_base_package_when_extraction_fails() -> None:
    representative = _article(
        url="https://example.com/article",
        publisher="Example News",
        published_date="2026-07-25T10:00:00Z",
        body="Alice spoke at the meeting.",
    )

    class FailingInfoExtractionService:
        async def extract(self, articles: list[object]) -> ExtractionResult:
            raise RuntimeError("Gemini is unavailable")

    service = PackageBuilderService(FailingInfoExtractionService())
    package = asyncio.run(
        service.build_full_package(
            "india", [DeduplicationGroup(representative=representative, duplicates=[])]
        )
    )

    assert package.entities == []
    assert package.events == []
    assert package.claims == []
    assert package.evidence == []
