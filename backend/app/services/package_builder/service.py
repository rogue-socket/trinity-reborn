"""Deterministic assembly of Layer 1 research packages."""

import logging
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from app.schemas.deduplication import DeduplicatedArticle, DeduplicationGroup
from app.schemas.package import Article, PackageMetadata, ResearchPackage, Source
from app.services.package_builder.llm_extraction import (
    ExtractionResult,
    InfoExtractionService,
)

UNKNOWN_PUBLISHER = "Unknown publisher"
logger = logging.getLogger(__name__)


class PackageBuilderService:
    """Build the non-LLM portion of a Layer 1 package for Layer 2 ingestion."""

    def __init__(
        self, info_extraction_service: InfoExtractionService | None = None
    ) -> None:
        """Optionally accept an extractor, deferring Gemini configuration until use."""
        self._info_extraction_service = info_extraction_service

    def build_base_package(
        self,
        topic_key: str,
        deduplicated_groups: list[DeduplicationGroup],
    ) -> ResearchPackage:
        """Build a valid package with articles and provenance but no extracted facts."""
        representatives = [group.representative for group in deduplicated_groups]
        sources, source_ids_by_publisher = self._build_sources(representatives)
        articles = self._build_articles(representatives, source_ids_by_publisher)

        return ResearchPackage(
            schema_version="1.0",
            package_id=str(uuid4()),
            topic_key=topic_key,
            metadata=PackageMetadata(
                title=topic_key,
                generated_at=datetime.now(UTC).isoformat(),
            ),
            sources=sources,
            articles=articles,
            evidence=[],
            entities=[],
            events=[],
            claims=[],
        )

    async def build_full_package(
        self,
        topic_key: str,
        deduplicated_groups: list[DeduplicationGroup],
    ) -> ResearchPackage:
        """Build a package and enrich it with facts when Gemini is available."""
        package = self.build_base_package(topic_key, deduplicated_groups)
        try:
            extractor = self._info_extraction_service or InfoExtractionService()
            extraction = await extractor.extract(package.articles)
        except Exception as error:
            logger.exception(
                "Package fact extraction unavailable: topic_key=%s error=%s",
                topic_key,
                error,
            )
            return package

        return self._merge_extraction(package, extraction)

    def _build_sources(
        self, articles: list[DeduplicatedArticle]
    ) -> tuple[list[Source], dict[str, str]]:
        """Create one package-local source entry for each publisher."""
        sources: list[Source] = []
        source_ids_by_publisher: dict[str, str] = {}

        for article in articles:
            publisher = article.publisher or UNKNOWN_PUBLISHER
            if publisher in source_ids_by_publisher:
                continue

            source_id = f"src_{len(sources) + 1:03d}"
            source_ids_by_publisher[publisher] = source_id
            sources.append(
                Source(
                    source_id=source_id,
                    publisher=publisher,
                    url=article.url,
                    published_at=article.published_date,
                )
            )

        return sources, source_ids_by_publisher

    @staticmethod
    def _merge_extraction(
        package: ResearchPackage, extraction: ExtractionResult
    ) -> ResearchPackage:
        """Return the base package enriched with validated Gemini output."""
        return package.model_copy(
            update={
                "entities": extraction.entities,
                "events": extraction.events,
                "claims": extraction.claims,
                "evidence": extraction.evidence,
                "relationships": extraction.relationships,
            }
        )

    def _build_articles(
        self,
        representatives: list[DeduplicatedArticle],
        source_ids_by_publisher: dict[str, str],
    ) -> list[Article]:
        """Build sequential article records from group representatives only."""
        return [
            Article(
                article_id=f"art_{index:03d}",
                source_id=source_ids_by_publisher[
                    representative.publisher or UNKNOWN_PUBLISHER
                ],
                canonical_url=representative.url,
                publisher=representative.publisher or UNKNOWN_PUBLISHER,
                published_at=representative.published_date,
                content_hash=self._generate_fingerprint(representative),
                content=representative.body,
            )
            for index, representative in enumerate(representatives, start=1)
        ]

    @staticmethod
    def _generate_fingerprint(article: DeduplicatedArticle) -> str:
        """Hash the PRD's article fingerprint inputs in a stable order."""
        publisher = article.publisher or UNKNOWN_PUBLISHER
        fingerprint_input = "\n".join(
            [article.url, publisher, article.published_date or "", article.body]
        )
        return sha256(fingerprint_input.encode("utf-8")).hexdigest()
