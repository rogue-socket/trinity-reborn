"""Tests for the article deduplication endpoint."""

from fastapi.testclient import TestClient

from app.api.dependencies import get_deduplication_service
from app.main import app
from app.schemas.deduplication import DeduplicatedArticle, DeduplicationGroup
from app.schemas.extraction import ExtractedArticle
from app.services.deduplication.service import DeduplicationService


def _article(
    *,
    url: str,
    title: str = "Example article",
    body: str,
    published_date: str = "2026-07-25",
    success: bool = True,
) -> ExtractedArticle:
    """Build an extracted article for deduplication tests."""
    return ExtractedArticle(
        url=url,
        title=title,
        publisher="Example",
        published_date=published_date,
        body=body,
        extraction_method="trafilatura",
        success=success,
        error=None if success else "Extraction failed",
    )


def test_deduplication_service_groups_near_identical_articles() -> None:
    first = _article(
        url="https://first.example/article",
        body=(
            "The city council approved the new river bridge after a unanimous vote "
            "on Tuesday evening."
        ),
    )
    second = _article(
        url="https://second.example/article",
        body=(
            "The city council approved the new river bridge after a unanimous vote "
            "on Tuesday evening, city officials said."
        ),
    )

    groups = DeduplicationService().deduplicate([first, second])

    assert len(groups) == 1
    assert len(groups[0].duplicates) == 1
    assert groups[0].duplicates[0].duplicate_of == groups[0].representative.url


def test_deduplication_service_groups_similar_titles_with_different_bodies() -> None:
    first = _article(
        url="https://first.example/article",
        title="Minister resigns after protests",
        body=(
            "Students marched through the capital after the government announced "
            "changes to its university admissions policy."
        ),
    )
    second = _article(
        url="https://second.example/article",
        title="Minister resigns after protests today",
        body=(
            "The cabinet accepted the education minister's resignation following "
            "weeks of demonstrations over leaked examination papers."
        ),
    )

    groups = DeduplicationService().deduplicate([first, second])

    assert len(groups) == 1
    assert len(groups[0].duplicates) == 1


def test_deduplication_service_keeps_distinct_topics_separate() -> None:
    bridge_article = _article(
        url="https://bridge.example/article",
        title="Council approves river bridge funding",
        body="The city council approved funding for a new river bridge project.",
    )
    sports_article = _article(
        url="https://sports.example/article",
        title="Football club wins championship final",
        body="The local football team won the championship after a dramatic final.",
    )

    groups = DeduplicationService().deduplicate([bridge_article, sports_article])

    assert len(groups) == 2
    assert all(not group.duplicates for group in groups)


def test_deduplication_service_excludes_failed_extractions() -> None:
    successful_article = _article(
        url="https://successful.example/article",
        body="The city council approved funding for a new river bridge project.",
    )
    failed_article = _article(
        url="https://failed.example/article",
        body="",
        success=False,
    )

    groups = DeduplicationService().deduplicate([successful_article, failed_article])

    assert len(groups) == 1
    assert groups[0].representative.url == successful_article.url
    assert groups[0].duplicates == []


def test_deduplication_service_prefers_longer_body_as_representative() -> None:
    shorter_article = _article(
        url="https://shorter.example/article",
        body="The city council approved funding for a new river bridge project.",
        published_date="2026-07-24",
    )
    longer_article = _article(
        url="https://longer.example/article",
        body=(
            "The city council approved funding for a new river bridge project. "
            "The bridge will improve access to the eastern district."
        ),
        published_date="2026-07-25",
    )

    groups = DeduplicationService(similarity_threshold=0).deduplicate(
        [shorter_article, longer_article]
    )

    assert len(groups) == 1
    assert groups[0].representative.url == longer_article.url


def test_deduplication_service_prefers_earliest_date_for_near_equal_bodies() -> None:
    later_article = _article(
        url="https://later.example/article",
        body="The city council approved funding for a new river bridge project. ",
        published_date="2026-07-25",
    )
    earlier_article = _article(
        url="https://earlier.example/article",
        body="The city council approved funding for a new river bridge project.",
        published_date="2026-07-24",
    )

    groups = DeduplicationService().deduplicate([later_article, earlier_article])

    assert groups[0].representative.url == earlier_article.url


def test_deduplicate_endpoint_delegates_to_service() -> None:
    article = ExtractedArticle(
        url="https://example.com/article",
        title="Article",
        publisher="Example",
        published_date="2026-07-25",
        body="Article body",
        extraction_method="trafilatura",
        success=True,
        error=None,
    )

    class FakeDeduplicationService:
        def deduplicate(
            self, articles: list[ExtractedArticle]
        ) -> list[DeduplicationGroup]:
            assert articles == [article]
            return [
                DeduplicationGroup(
                    representative=DeduplicatedArticle(
                        url=article.url,
                        title=article.title,
                        publisher=article.publisher,
                        published_date=article.published_date,
                        body=article.body,
                        duplicate_of=None,
                    ),
                    duplicates=[],
                )
            ]

    async def override_service() -> FakeDeduplicationService:
        return FakeDeduplicationService()

    app.dependency_overrides[get_deduplication_service] = override_service
    try:
        response = TestClient(app).post(
            "/deduplicate",
            json={"articles": [article.model_dump(mode="json")]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["groups"][0]["representative"]["url"] == article.url


def test_deduplicate_endpoint_rejects_empty_article_list() -> None:
    response = TestClient(app).post("/deduplicate", json={"articles": []})

    assert response.status_code == 400
    assert response.json()["detail"] == "At least one article is required."
