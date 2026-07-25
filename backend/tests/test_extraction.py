"""Tests for best-effort article extraction."""

import asyncio

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api.dependencies import get_extraction_service
from app.main import app
from app.schemas.extraction import ExtractedArticle
from app.services.extraction.service import ExtractionService, _ExtractionContent

GOOD_BODY = "x" * 200


def test_extraction_service_uses_trafilatura(monkeypatch: MonkeyPatch) -> None:
    service = ExtractionService()

    monkeypatch.setattr(
        service,
        "_extract_with_trafilatura",
        lambda url: _ExtractionContent("Title", "Publisher", "2026-07-25", GOOD_BODY),
    )
    monkeypatch.setattr(
        service,
        "_extract_with_newspaper",
        lambda url: (_ for _ in ()).throw(AssertionError("Fallback was unexpected")),
    )

    article = asyncio.run(service.extract(["https://example.com/good"]))[0]

    assert article.success is True
    assert article.extraction_method == "trafilatura"
    assert article.body == GOOD_BODY


def test_extraction_service_resolves_google_news_url_before_extracting(
    monkeypatch: MonkeyPatch,
) -> None:
    service = ExtractionService()
    wrapper_url = "https://news.google.com/rss/articles/example"
    final_url = "https://publisher.example/article"

    monkeypatch.setattr(
        "app.services.extraction.service.gnewsdecoder",
        lambda url: {"status": True, "decoded_url": final_url},
    )
    monkeypatch.setattr(
        service,
        "_extract_with_trafilatura",
        lambda url: _ExtractionContent(url, None, None, GOOD_BODY),
    )

    article = asyncio.run(service.extract([wrapper_url]))[0]

    assert article.success is True
    assert article.url == wrapper_url
    assert article.title == final_url


def test_extraction_service_falls_back_to_newspaper(monkeypatch: MonkeyPatch) -> None:
    service = ExtractionService()

    monkeypatch.setattr(
        service,
        "_extract_with_trafilatura",
        lambda url: _ExtractionContent("Title", None, None, "too short"),
    )
    monkeypatch.setattr(
        service,
        "_extract_with_newspaper",
        lambda url: _ExtractionContent("Fallback", "Publisher", None, GOOD_BODY),
    )

    article = asyncio.run(service.extract(["https://example.com/fallback"]))[0]

    assert article.success is True
    assert article.extraction_method == "newspaper4k"
    assert article.title == "Fallback"


def test_extraction_service_returns_failure_when_both_extractors_fail(
    monkeypatch: MonkeyPatch,
) -> None:
    service = ExtractionService()

    def fail(url: str) -> _ExtractionContent:
        raise RuntimeError("network error")

    monkeypatch.setattr(service, "_extract_with_trafilatura", fail)
    monkeypatch.setattr(service, "_extract_with_newspaper", fail)

    article = asyncio.run(service.extract(["https://example.com/bad"]))[0]

    assert article.success is False
    assert article.body == ""
    assert article.error is not None
    assert "network error" in article.error


def test_extract_endpoint_returns_mixed_batch_results() -> None:
    class FakeExtractionService:
        async def extract(self, urls: list[str]) -> list[ExtractedArticle]:
            return [
                ExtractedArticle(
                    url=url,
                    title="Title" if url != "https://bad.example" else "",
                    publisher="Publisher" if url != "https://bad.example" else None,
                    published_date=None,
                    body=GOOD_BODY if url != "https://bad.example" else "",
                    extraction_method="trafilatura",
                    success=url != "https://bad.example",
                    error=(
                        None
                        if url != "https://bad.example"
                        else "Unable to download URL"
                    ),
                )
                for url in urls
            ]

    async def override_service() -> FakeExtractionService:
        return FakeExtractionService()

    app.dependency_overrides[get_extraction_service] = override_service
    try:
        response = TestClient(app).post(
            "/extract",
            json={
                "urls": [
                    "https://good-one.example",
                    "https://good-two.example",
                    "https://bad.example",
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [article["success"] for article in response.json()["articles"]] == [
        True,
        True,
        False,
    ]


def test_extract_endpoint_rejects_empty_url_list() -> None:
    response = TestClient(app).post("/extract", json={"urls": []})

    assert response.status_code == 400
    assert response.json() == {"detail": "At least one URL is required."}
