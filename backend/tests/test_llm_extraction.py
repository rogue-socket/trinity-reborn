"""Tests for Gemini-backed information extraction without live API calls."""

import asyncio
import json

import pytest
from pytest import MonkeyPatch

from app.schemas.package import Article
from app.services.package_builder.llm_extraction import (
    GeminiConfigurationError,
    InfoExtractionService,
)


def _article(article_id: str = "art_source") -> Article:
    """Build an immutable article with a known evidence substring."""
    content = "Minister Alice resigned after protests in the capital."
    return Article(
        article_id=article_id,
        source_id="src_001",
        canonical_url="https://example.com/article",
        publisher="Example News",
        published_at="2026-07-25T10:00:00Z",
        content_hash="a" * 64,
        content=content,
        language="en",
    )


def _valid_response(article: Article) -> str:
    """Return a valid mocked Gemini payload using temporary local IDs."""
    excerpt = "Alice resigned"
    start_offset = article.content.index(excerpt)
    return json.dumps(
        {
            "entities": [
                {
                    "entity_id": "ent_local",
                    "label": "Alice",
                    "type": "person",
                    "aliases": [],
                    "evidence_ids": ["ev_local"],
                }
            ],
            "events": [
                {
                    "event_id": "evt_local",
                    "type": "resignation",
                    "title": "Alice resigned",
                    "description": "Alice resigned after protests.",
                    "temporal": {
                        "start": "2026-07-25",
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
                    "predicate_candidate": "RESIGNED_AFTER",
                    "object_ref_or_value": "protests",
                    "temporal_scope": {
                        "start": "2026-07-25",
                        "precision": "day",
                        "basis": "reported",
                    },
                    "asserted_by_entity_id": None,
                    "epistemic_status": "reported",
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev_local",
                    "article_id": article.article_id,
                    "excerpt": excerpt,
                    "start_offset": start_offset,
                    "end_offset": start_offset + len(excerpt),
                    "language": "en",
                }
            ],
            "relationships": [
                {
                    "relationship_id": "rel_local",
                    "subject_ref": "ent_local",
                    "object_ref": "evt_local",
                    "source_relation_label": "resigned",
                    "evidence_ids": ["ev_local"],
                    "extraction_confidence": 0.9,
                }
            ],
        }
    )


def test_info_extraction_assigns_package_local_ids(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    article = _article()
    service = InfoExtractionService()
    monkeypatch.setattr(
        service, "_generate_json", lambda prompt: _valid_response(article)
    )

    result = asyncio.run(service.extract([article]))

    assert [entity.entity_id for entity in result.entities] == ["ent_001"]
    assert [event.event_id for event in result.events] == ["evt_001"]
    assert [claim.claim_id for claim in result.claims] == ["clm_001"]
    assert [evidence.evidence_id for evidence in result.evidence] == ["ev_001"]
    assert [relationship.relationship_id for relationship in result.relationships] == [
        "rel_001"
    ]
    assert result.claims[0].event_id == "evt_001"
    assert result.claims[0].subject_ref == "ent_001"
    assert result.evidence[0].excerpt == "Alice resigned"


def test_info_extraction_skips_invalid_model_json(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    article = _article()
    service = InfoExtractionService()
    monkeypatch.setattr(service, "_generate_json", lambda prompt: "not valid json")

    result = asyncio.run(service.extract([article]))

    assert result.entities == []
    assert result.events == []
    assert result.claims == []
    assert result.evidence == []
    assert result.relationships == []


def test_info_extraction_requires_gemini_api_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        InfoExtractionService()
