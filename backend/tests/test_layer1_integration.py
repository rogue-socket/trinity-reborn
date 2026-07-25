import asyncio
import uuid

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api import layer1 as layer1_api
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import app
from app.models import DiscoveredArticleRecord, DiscoveryRequest
from app.services import layer1


def _article(*, url: str, canonical_url: str, publisher: str) -> dict:
    return {
        "url": url,
        "canonical_url": canonical_url,
        "title": "Election update",
        "publisher": publisher,
        "published_date": "2026-07-25T10:00:00Z",
        "body": "A" * 240,
        "extraction_method": "trafilatura",
        "success": True,
        "error": None,
    }


def test_layer1_package_is_provenance_complete_and_ingestable() -> None:
    topic_key = f"layer1-handoff-{uuid.uuid4().hex}"
    first = _article(
        url="https://news.google.com/rss/articles/first",
        canonical_url="https://example.com/first",
        publisher="Example News",
    )
    second = _article(
        url="https://news.google.com/rss/articles/second",
        canonical_url="https://example.net/second",
        publisher="Second News",
    )

    with TestClient(app) as client:
        topic = client.post(
            "/topics",
            json={
                "topic_key": topic_key,
                "display_name": "Layer 1 integration",
                "scope": {"description": "A test topic.", "geography": [], "start": "2026-07-25"},
            },
        )
        assert topic.status_code == 201

        groups = client.post("/deduplicate", json={"articles": [first, second]})
        package = client.post("/build-package", json={"topic_key": topic_key, "articles": [first, second]})
        ingestion = client.post("/ingestions", json=package.json())

    assert len(groups.json()["groups"]) == 1
    assert package.status_code == 200
    body = package.json()
    assert len(body["articles"]) == 2
    assert body["articles"][0]["canonical_url"] == first["canonical_url"]
    assert body["articles"][0]["discovery_url"] == first["url"]
    assert len(body["sources"]) == 2
    assert ingestion.status_code == 201
    assert ingestion.json()["status"] == "accepted"


def test_discovery_persists_its_topic_and_results(monkeypatch) -> None:
    topic_key = f"discovery-{uuid.uuid4().hex}"

    monkeypatch.setattr(
        "app.api.layer1.discover",
        lambda topic, limit: [
            layer1.DiscoveredArticle(
                title="Discovery result",
                publisher="Example News",
                published_date="2026-07-25T10:00:00Z",
                url="https://news.google.com/rss/articles/example",
            )
        ],
    )
    with TestClient(app) as client:
        response = client.get("/discover", params={"topic": topic_key, "limit": 3})

    assert response.status_code == 200
    with Session(get_engine()) as session:
        request = session.scalar(
            select(DiscoveryRequest).where(DiscoveryRequest.topic_key == topic_key)
        )
        assert request is not None
        assert request.requested_limit == 3
        assert request.status == "completed"
        article = session.scalar(
            select(DiscoveredArticleRecord).where(
                DiscoveredArticleRecord.discovery_request_id == request.id
            )
        )
    assert article is not None
    assert article.title == "Discovery result"


def test_discovery_history_failure_does_not_discard_results() -> None:
    class BrokenSession:
        rolled_back = False

        def add(self, _: object) -> None:
            pass

        def add_all(self, _: object) -> None:
            pass

        def flush(self) -> None:
            pass

        def commit(self) -> None:
            raise SQLAlchemyError("database unavailable")

        def rollback(self) -> None:
            self.rolled_back = True

    session = BrokenSession()
    layer1_api._persist_discovery(
        session,  # type: ignore[arg-type]
        "failed-history",
        1,
        "completed",
        [],
    )

    assert session.rolled_back is True


def test_extraction_keeps_the_discovery_url_and_uses_the_publisher_url(monkeypatch) -> None:
    discovery_url = "https://news.google.com/rss/articles/example"
    canonical_url = "https://example.com/story"
    monkeypatch.setattr(layer1, "_decode_google_news_url", lambda url: canonical_url)
    monkeypatch.setattr(
        layer1,
        "_extract_with_trafilatura",
        lambda url: ("Story", "Example News", "2026-07-25", "A" * 240),
    )

    article = layer1._extract_one(discovery_url)

    assert article.success is True
    assert article.url == discovery_url
    assert article.canonical_url == canonical_url


def test_extract_endpoint_preserves_the_layer1_response_envelope(monkeypatch) -> None:
    extracted = layer1.ExtractedArticle(
        **_article(
            url="https://news.google.com/rss/articles/example",
            canonical_url="https://example.com/story",
            publisher="Example News",
        )
    )

    async def fake_extract(urls: list[str]) -> list[layer1.ExtractedArticle]:
        assert urls == [extracted.url]
        return [extracted]

    monkeypatch.setattr("app.api.layer1.extract", fake_extract)
    with TestClient(app) as client:
        response = client.post("/extract", json={"urls": [extracted.url]})

    assert response.status_code == 200
    assert response.json() == {"articles": [extracted.model_dump(mode="json")]}


def test_fact_normalization_maps_layer1_labels_to_the_l2_entity_contract() -> None:
    article = layer1.Article(
        article_id="art_001",
        source_id="src_001",
        canonical_url="https://example.com/article",
        publisher="Example News",
        content_hash="a" * 64,
        content="Alice announced the result.",
    )
    facts = layer1._normalize_facts(
        article,
        {
            "evidence": [
                {
                    "evidence_id": "ev_local",
                    "article_id": "art_001",
                    "excerpt": "Alice",
                    "start_offset": 0,
                    "end_offset": 5,
                    "language": "en",
                }
            ],
            "entities": [
                {
                    "entity_id": "ent_local",
                    "label": "Alice",
                    "type": "person",
                    "aliases": [],
                    "evidence_ids": ["ev_local"],
                }
            ],
            "events": [],
            "claims": [],
            "relationships": [],
        },
        1,
    )

    assert facts.entities[0].model_dump() == {
        "entity_id": "ent_001_001",
        "name": "Alice",
        "type": "person",
        "aliases": [],
        "evidence_ids": ["ev_001_001"],
    }


def test_package_extracts_facts_once_per_deduplication_representative() -> None:
    first = layer1.ExtractedArticle(
        **_article(
            url="https://news.google.com/rss/articles/first",
            canonical_url="https://example.com/first",
            publisher="Example News",
        )
    )
    duplicate = first.model_copy(
        update={
            "url": "https://news.google.com/rss/articles/duplicate",
            "canonical_url": "https://example.net/duplicate",
        }
    )
    calls: list[str] = []

    def fake_generator(article: layer1.Article) -> dict:
        calls.append(article.article_id)
        return {"evidence": [], "entities": [], "events": [], "claims": [], "relationships": []}

    package = asyncio.run(
        layer1.build_full_package(
            layer1.PackageBuildRequest(topic_key="test-topic", articles=[first, duplicate]),
            fact_generator=fake_generator,
        )
    )

    assert len(package.articles) == 2
    assert calls == ["art_001"]


def test_valid_generated_facts_are_accepted_by_layer2() -> None:
    topic_key = f"generated-facts-{uuid.uuid4().hex}"
    content = "Alice resigned after protests. " + "Context. " * 30
    article = layer1.ExtractedArticle(
        url="https://news.google.com/rss/articles/facts",
        canonical_url="https://example.com/facts",
        title="Alice resigns",
        publisher="Example News",
        published_date="2026-07-25T10:00:00Z",
        body=content,
        extraction_method="trafilatura",
        success=True,
    )
    excerpt = "Alice resigned"
    offset = content.index(excerpt)

    def fake_generator(_: layer1.Article) -> dict:
        return {
            "evidence": [
                {
                    "evidence_id": "ev_local",
                    "article_id": "art_001",
                    "excerpt": excerpt,
                    "start_offset": offset,
                    "end_offset": offset + len(excerpt),
                }
            ],
            "entities": [
                {
                    "entity_id": "ent_local",
                    "label": "Alice",
                    "type": "person",
                    "evidence_ids": ["ev_local"],
                }
            ],
            "events": [
                {
                    "event_id": "evt_local",
                    "type": "resignation",
                    "title": "Alice resigned",
                    "temporal": {
                        "start": "2026-07-25T00:00:00Z",
                        "precision": "day",
                        "basis": "reported",
                    },
                    "participant_entity_ids": ["ent_local"],
                    "location_entity_ids": [],
                    "evidence_ids": ["ev_local"],
                    "related_claim_ids": ["clm_local"],
                }
            ],
            "claims": [
                {
                    "claim_id": "clm_local",
                    "text": "Alice resigned after protests.",
                    "evidence_ids": ["ev_local"],
                    "event_id": "evt_local",
                    "subject_ref": "ent_local",
                    "predicate_candidate": "resigned",
                    "object_ref_or_value": "after protests",
                    "temporal_scope": {
                        "start": "2026-07-25T00:00:00Z",
                        "precision": "day",
                        "basis": "reported",
                    },
                    "asserted_by_entity_id": None,
                    "epistemic_status": "reported",
                }
            ],
            "relationships": [
                {
                    "relationship_id": "rel_local",
                    "subject_ref": "ent_local",
                    "object_ref": "evt_local",
                    "source_relation_label": "participated in",
                    "evidence_ids": ["ev_local"],
                    "extraction_confidence": 0.9,
                }
            ],
        }

    package = asyncio.run(
        layer1.build_full_package(
            layer1.PackageBuildRequest(topic_key=topic_key, articles=[article]),
            fact_generator=fake_generator,
        )
    )
    with TestClient(app) as client:
        topic = client.post(
            "/topics",
            json={
                "topic_key": topic_key,
                "display_name": "Generated facts",
                "scope": {"description": "A test topic.", "geography": [], "start": "2026-07-25"},
            },
        )
        ingestion = client.post("/ingestions", json=package.model_dump(mode="json"))

    assert topic.status_code == 201
    assert ingestion.status_code == 201
    assert ingestion.json()["status"] == "accepted"


def test_fact_normalization_rejects_values_layer2_would_reject() -> None:
    article = layer1.Article(
        article_id="art_001",
        source_id="src_001",
        canonical_url="https://example.com/article",
        publisher="Example News",
        content_hash="a" * 64,
        content="Alice resigned.",
    )

    with pytest.raises(ValidationError):
        layer1._normalize_facts(
            article,
            {
                "evidence": [],
                "entities": [],
                "events": [],
                "claims": [
                    {
                        "claim_id": "claim",
                        "text": "Alice resigned.",
                        "event_id": "event",
                        "subject_ref": "entity",
                        "predicate_candidate": "resigned",
                        "object_ref_or_value": "office",
                        "temporal_scope": {
                            "start": "not-a-date",
                            "precision": "invalid",
                            "basis": "guessed",
                        },
                        "epistemic_status": "certain",
                    }
                ],
                "relationships": [],
            },
            1,
        )


def test_invalid_model_output_is_excluded_without_invalidating_the_package() -> None:
    article = layer1.ExtractedArticle(
        **_article(
            url="https://news.google.com/rss/articles/invalid",
            canonical_url="https://example.com/invalid",
            publisher="Example News",
        )
    )

    def invalid_generator(_: layer1.Article) -> dict:
        return {"entities": [{"entity_id": "bad"}]}

    package = asyncio.run(
        layer1.build_full_package(
            layer1.PackageBuildRequest(topic_key="test-topic", articles=[article]),
            fact_generator=invalid_generator,
        )
    )

    assert package.entities == []
    assert package.events == []
    assert package.claims == []
