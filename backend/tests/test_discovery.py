"""Tests for Google News RSS discovery."""

import asyncio
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api.dependencies import get_discovery_workflow
from app.main import app
from app.models.discovery import DiscoveryRequest
from app.schemas.discovery import DiscoveredArticle
from app.services.discovery.service import (
    DiscoveryError,
    GoogleNewsDiscoveryService,
    build_google_news_rss_url,
)
from app.services.discovery.workflow import DiscoveryWorkflow


def test_discovery_service_normalizes_rss_entries(monkeypatch: MonkeyPatch) -> None:
    def fake_parse(url: str) -> dict[str, Any]:
        assert url == build_google_news_rss_url("india")
        return {
            "entries": [
                {
                    "title": "A current-affairs headline",
                    "source": {"title": "Example News"},
                    "published": "Fri, 24 Jul 2026 10:00:00 GMT",
                    "link": "https://news.google.com/articles/example",
                }
            ]
        }

    monkeypatch.setattr("app.services.discovery.service.feedparser.parse", fake_parse)

    articles = GoogleNewsDiscoveryService().discover(topic="india", limit=1)

    assert [article.model_dump() for article in articles] == [
        {
            "headline": "A current-affairs headline",
            "publisher": "Example News",
            "published_date": "Fri, 24 Jul 2026 10:00:00 GMT",
            "url": "https://news.google.com/articles/example",
        }
    ]


def test_discovery_workflow_persists_successful_results() -> None:
    articles = [
        {
            "headline": "A current-affairs headline",
            "publisher": "Example News",
            "published_date": "Fri, 24 Jul 2026 10:00:00 GMT",
            "url": "https://news.google.com/articles/example",
        }
    ]
    class FakeRepository:
        def __init__(self) -> None:
            self.request = DiscoveryRequest(source_url="https://news.google.com/rss")
            self.saved_articles: list[DiscoveredArticle] = []

        async def create_request(self, source_url: str) -> DiscoveryRequest:
            assert source_url == "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
            return self.request

        async def save_success(
            self,
            request: DiscoveryRequest,
            discovered_articles: list[DiscoveredArticle],
        ) -> None:
            assert request is self.request
            self.saved_articles = discovered_articles

        async def mark_failed(self, request: DiscoveryRequest) -> None:
            raise AssertionError(f"Unexpected failed request: {request}")

    class FakeDiscoveryService:
        def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
            assert topic == "india"
            assert limit == 1
            return [DiscoveredArticle.model_validate(article) for article in articles]

    repository = FakeRepository()
    workflow = DiscoveryWorkflow(FakeDiscoveryService(), repository)

    discovered_articles = asyncio.run(workflow.discover(topic="india", limit=1))

    assert [article.model_dump() for article in discovered_articles] == articles
    assert [article.model_dump() for article in repository.saved_articles] == articles


def test_discovery_workflow_marks_failed_requests() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.request = DiscoveryRequest(source_url="https://news.google.com/rss")
            self.failed = False

        async def create_request(self, source_url: str) -> DiscoveryRequest:
            assert source_url == "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
            return self.request

        async def save_success(
            self,
            request: DiscoveryRequest,
            articles: list[DiscoveredArticle],
        ) -> None:
            raise AssertionError("Unexpected successful request")

        async def mark_failed(self, request: DiscoveryRequest) -> None:
            assert request is self.request
            self.failed = True

    class FailingDiscoveryService:
        def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
            raise DiscoveryError("RSS unavailable")

    repository = FakeRepository()
    workflow = DiscoveryWorkflow(FailingDiscoveryService(), repository)

    try:
        asyncio.run(workflow.discover(topic="india", limit=1))
    except DiscoveryError:
        pass
    else:
        raise AssertionError("Expected discovery to fail")

    assert repository.failed is True


def test_discover_endpoint_returns_articles() -> None:
    articles = [
        {
            "headline": "A current-affairs headline",
            "publisher": "Example News",
            "published_date": "Fri, 24 Jul 2026 10:00:00 GMT",
            "url": "https://news.google.com/articles/example",
        }
    ]

    class FakeWorkflow:
        async def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
            assert topic == "india"
            discovered_articles = [
                DiscoveredArticle.model_validate(article) for article in articles
            ]
            return discovered_articles[:limit]

    async def override_workflow() -> FakeWorkflow:
        return FakeWorkflow()

    app.dependency_overrides[get_discovery_workflow] = override_workflow

    try:
        response = TestClient(app).get("/discover?topic=india&limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == articles


def test_discover_endpoint_limit_changes_article_count() -> None:
    articles = [
        {
            "headline": f"Headline {number}",
            "publisher": "Example News",
            "published_date": "Fri, 24 Jul 2026 10:00:00 GMT",
            "url": f"https://news.google.com/articles/{number}",
        }
        for number in range(3)
    ]

    class FakeWorkflow:
        async def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
            assert topic == "india"
            discovered_articles = [
                DiscoveredArticle.model_validate(article) for article in articles
            ]
            return discovered_articles[:limit]

    async def override_workflow() -> FakeWorkflow:
        return FakeWorkflow()

    app.dependency_overrides[get_discovery_workflow] = override_workflow
    try:
        client = TestClient(app)
        one_article = client.get("/discover?topic=india&limit=1")
        three_articles = client.get("/discover?topic=india&limit=3")
    finally:
        app.dependency_overrides.clear()

    assert one_article.status_code == 200
    assert three_articles.status_code == 200
    assert len(one_article.json()) == 1
    assert len(three_articles.json()) == 3


def test_discover_endpoint_requires_topic() -> None:
    response = TestClient(app).get("/discover")

    assert response.status_code == 400
    assert response.json() == {"detail": "A topic query parameter is required."}


def test_discover_endpoint_returns_articles_when_persistence_fails(
    caplog: Any,
) -> None:
    article = DiscoveredArticle(
        headline="A current-affairs headline",
        publisher="Example News",
        published_date="Fri, 24 Jul 2026 10:00:00 GMT",
        url="https://news.google.com/articles/example",
    )

    class FailingRepository:
        async def create_request(self, source_url: str) -> DiscoveryRequest:
            raise RuntimeError("Postgres unavailable")

        async def save_success(
            self, request: DiscoveryRequest, articles: list[DiscoveredArticle]
        ) -> None:
            raise AssertionError("save_success should not be reached")

        async def mark_failed(self, request: DiscoveryRequest) -> None:
            raise AssertionError("mark_failed should not be reached")

    class FakeDiscoveryService:
        def discover(self, topic: str, limit: int) -> list[DiscoveredArticle]:
            assert topic == "india"
            return [article][:limit]

    async def override_workflow() -> DiscoveryWorkflow:
        return DiscoveryWorkflow(FakeDiscoveryService(), FailingRepository())

    app.dependency_overrides[get_discovery_workflow] = override_workflow
    try:
        with caplog.at_level("ERROR"):
            response = TestClient(app).get("/discover?topic=india&limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [article.model_dump()]
    assert "Postgres unavailable" in caplog.text
    assert "india" in caplog.text
