import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import app
from app.models import (
    ArticleVersion,
    CanonicalEntity,
    CanonicalEvent,
    ClaimMention,
    Claim,
    ClaimAssertion,
    ClaimStatusHistory,
    ConfidenceAssessment,
    EntityMention,
    EventMention,
    EventResolutionContext,
    EvidenceMention,
    RawPackage,
    RejectedPackage,
    RelationshipMention,
    SourceMention,
    Topic,
    LocalIdMapping,
    GraphRelationship,
    IngestionRun,
    RelationshipAssertion,
    RelationshipStatusHistory,
    ProvenanceLink,
    ResolutionDecision,
)
from app.policy import CANDIDATE_LIMIT


def register_topic(client: TestClient) -> str:
    topic_key = f"ingestion-topic-{uuid.uuid4().hex}"
    response = client.post(
        "/topics",
        json={
            "topic_key": topic_key,
            "display_name": "Ingestion test topic",
            "scope": {
                "description": "A bounded implementation test topic.",
                "geography": [],
                "start": "2026-07-01",
                "end": None,
            },
        },
    )
    assert response.status_code == 201
    return topic_key


def test_stores_a_new_package_and_returns_an_idempotent_retry() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        payload = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "Initial delivery", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [],
            "events": [],
            "claims": [],
        }

        created = client.post("/ingestions", json=payload)
        retried = client.post("/ingestions", json=payload)

    assert created.status_code == 201
    assert retried.status_code == 200
    assert retried.json()["ingestion_id"] == created.json()["ingestion_id"]
    assert created.json()["package_id"] == payload["package_id"]
    assert created.json()["input_schema_version"] == "1.0"
    assert created.json()["graph_model_version"] == "kg-model-0.1"
    assert created.json()["pipeline_version"] == "kg-pipeline-0.2"
    assert created.json()["ontology_version"] == "kg-ontology-0.2"
    assert created.json()["processing_duration_ms"] >= 0
    assert retried.json()["processing_duration_ms"] == created.json()["processing_duration_ms"]
    with Session(get_engine()) as session:
        run = session.get(IngestionRun, uuid.UUID(created.json()["ingestion_id"]))
        assert run is not None
        assert run.report_json["processing_duration_ms"] == created.json()["processing_duration_ms"]


def test_prevents_raw_package_mutation() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        payload = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "Immutable delivery", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [],
            "events": [],
            "claims": [],
        }
        created = client.post("/ingestions", json=payload)

    assert created.status_code == 201
    with Session(get_engine()) as session:
        run = session.get(IngestionRun, uuid.UUID(created.json()["ingestion_id"]))
        assert run is not None
        with pytest.raises(DBAPIError):
            session.execute(update(RawPackage).where(RawPackage.id == run.raw_package_id).values(revision=2))
            session.commit()
        session.rollback()


def test_prevents_source_derived_mutation() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Immutable source", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [{"source_id": "src-1"}],
                "articles": [{"article_id": "art-1", "source_id": "src-1", "content": "Original text"}],
                "evidence": [{"evidence_id": "ev-1", "article_id": "art-1", "excerpt": "Original", "start_offset": 0, "end_offset": 8}],
                "entities": [], "events": [], "claims": [],
            },
        )

    assert response.status_code == 201
    with Session(get_engine()) as session:
        article = session.scalar(select(ArticleVersion).where(ArticleVersion.content == "Original text"))
        assert article is not None
        with pytest.raises(DBAPIError):
            session.execute(update(ArticleVersion).where(ArticleVersion.id == article.id).values(content="Changed"))
        session.rollback()


def test_rejects_a_package_for_an_unknown_topic() -> None:
    payload = {
        "schema_version": "1.0",
        "package_id": str(uuid.uuid4()),
        "topic_key": "missing-topic",
        "metadata": {"title": "Initial delivery", "generated_at": "2026-07-25T10:30:00Z"},
        "sources": [],
        "articles": [],
        "evidence": [],
        "entities": [],
        "events": [],
        "claims": [],
    }

    with TestClient(app) as client:
        response = client.post("/ingestions", json=payload)

    assert response.status_code == 404


def test_retains_invalid_json_with_a_rejection_report() -> None:
    raw_body = b'{"schema_version":"1.0"'
    with TestClient(app) as client:
        response = client.post("/ingestions", content=raw_body, headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    with Session(get_engine()) as session:
        rejected = session.scalar(
            select(RejectedPackage).where(RejectedPackage.payload_checksum == hashlib.sha256(raw_body).hexdigest())
        )
        assert rejected is not None
        assert rejected.payload_bytes == raw_body
        assert rejected.report_json["status"] == "rejected"


def test_retains_unsupported_schema_and_unknown_topic_rejections() -> None:
    unsupported_id = str(uuid.uuid4())
    unknown_id = str(uuid.uuid4())
    base = {
        "metadata": {"title": "Rejected delivery", "generated_at": "2026-07-25T10:30:00Z"},
        "sources": [],
        "articles": [],
        "evidence": [],
        "entities": [],
        "events": [],
        "claims": [],
    }
    with TestClient(app) as client:
        unsupported = client.post(
            "/ingestions",
            json={**base, "schema_version": "9.0", "package_id": unsupported_id, "topic_key": "missing-topic"},
        )
        unknown = client.post(
            "/ingestions",
            json={**base, "schema_version": "1.0", "package_id": unknown_id, "topic_key": "missing-topic"},
        )

    assert unsupported.status_code == 400
    assert unknown.status_code == 404
    with Session(get_engine()) as session:
        rejected = list(
            session.scalars(
                select(RejectedPackage).where(RejectedPackage.package_id.in_([uuid.UUID(unsupported_id), uuid.UUID(unknown_id)]))
            )
        )
        assert {item.package_id for item in rejected} == {uuid.UUID(unsupported_id), uuid.UUID(unknown_id)}


def test_stores_a_changed_delivery_as_a_new_revision() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        payload = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First delivery", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [],
            "events": [],
            "claims": [],
        }
        first = client.post("/ingestions", json=payload)
        payload["metadata"]["title"] = "Revised delivery"
        revised = client.post("/ingestions", json=payload)

    assert first.status_code == 201
    assert revised.status_code == 201
    assert revised.json()["ingestion_id"] != first.json()["ingestion_id"]


def test_partially_accepts_independent_valid_objects() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        payload = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "Mixed delivery", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [{"article_id": "art-1", "source_id": "missing-source", "content": "Text"}],
            "evidence": [],
            "entities": [],
            "events": [],
            "claims": [],
        }
        response = client.post("/ingestions", json=payload)

    assert response.status_code == 201
    assert response.json()["status"] == "partially_accepted"
    assert response.json()["summary"] == {
        "accepted": 1,
        "rejected": 1,
        "created": 0,
        "matched": 0,
        "possible_matches": 0,
        "contradictions": 0,
    }


def test_accepts_evidence_free_claims_and_relationships_with_warnings() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Evidence-free material",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {"entity_id": "ent-1", "type": "organization", "name": "Example Group"}
                ],
                "events": [],
                "claims": [
                    {
                        "claim_id": "clm-1",
                        "text": "Example Group made an announcement.",
                        "subject_ref": "ent-1",
                    }
                ],
                "relationships": [
                    {
                        "relationship_id": "rel-1",
                        "subject_ref": "ent-1",
                        "object_ref": "clm-1",
                        "source_relation_label": "announced",
                    }
                ],
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "accepted_with_warnings"
    results = {item["local_id"]: item for item in body["object_results"]}
    assert results["clm-1"]["status"] == "accepted_with_warnings"
    assert results["rel-1"]["status"] == "accepted_with_warnings"
    assert {warning["local_id"] for warning in body["warnings"]} == {"clm-1", "rel-1"}

    with Session(get_engine()) as session:
        claim_id = uuid.UUID(results["clm-1"]["canonical_id"])
        confidence_values = list(
            session.scalars(
                select(ConfidenceAssessment.value).where(
                    ConfidenceAssessment.subject_id.in_(
                        [
                            uuid.UUID(results["clm-1"]["canonical_id"]),
                            uuid.UUID(results["rel-1"]["canonical_id"]),
                        ]
                    )
                )
            )
        )
        session.add(
            ConfidenceAssessment(
                subject_type="claim",
                subject_id=claim_id,
                dimension="interpretation",
                value=0.99,
                assessed_by="layer_2_rule",
                method="test_interpretation_signal",
                model_or_rule_version="kg-pipeline-0.2",
                supporting_ids=[],
                rationale="A high unrelated dimension must not satisfy claim-support filtering.",
            )
        )
        session.commit()
    assert confidence_values
    assert max(confidence_values) < 0.7

    with TestClient(app) as client:
        filtered = client.get(
            f"/topics/{body['topic_id']}/context",
            params={"minimum_confidence": 0.7},
        )

    assert claim_id not in {
        uuid.UUID(item["claim_id"]) for item in filtered.json()["claims"]
    }


def test_rejects_relationship_when_its_event_dependency_is_rejected() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Dependency-aware validation",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [{"source_id": "src-1"}],
                "articles": [],
                "evidence": [],
                "entities": [
                    {
                        "entity_id": "ent-independent",
                        "type": "organization",
                        "name": "Independent entity",
                    }
                ],
                "events": [
                    {
                        "event_id": "evt-invalid",
                        "type": "meeting",
                        "title": "Invalid event",
                        "temporal": {
                            "end": "2026-07-25T12:00:00Z",
                            "precision": "minute",
                            "basis": "reported",
                        },
                    }
                ],
                "claims": [],
                "relationships": [
                    {
                        "relationship_id": "rel-invalid",
                        "subject_ref": "ent-independent",
                        "object_ref": "evt-invalid",
                        "source_relation_label": "participated in",
                    }
                ],
            },
        )

        assert response.status_code == 201
        body = response.json()
        results = {item["local_id"]: item for item in body["object_results"]}
        assert body["status"] == "partially_accepted"
        assert results["ent-independent"]["status"] == "accepted"
        assert results["evt-invalid"]["errors"] == ["invalid temporal value"]
        assert results["rel-invalid"]["errors"] == [
            "object_ref depends on rejected object: evt-invalid"
        ]

        context = client.get(f"/topics/{body['topic_id']}/context")

    assert [item["label"] for item in context.json()["entities"]] == ["Independent entity"]
    assert context.json()["events"] == []
    assert context.json()["relationships"] == []


def test_transitively_rejects_objects_that_depend_on_a_rejected_event() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Transitive dependency validation",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [{"source_id": "src-1"}],
                "articles": [],
                "evidence": [],
                "entities": [
                    {
                        "entity_id": "ent-independent",
                        "type": "organization",
                        "name": "Independent entity",
                    }
                ],
                "events": [
                    {
                        "event_id": "evt-invalid",
                        "type": "meeting",
                        "title": "Invalid event",
                        "temporal": {
                            "end": "2026-07-25T12:00:00Z",
                            "precision": "minute",
                            "basis": "reported",
                        },
                    }
                ],
                "claims": [
                    {
                        "claim_id": "clm-dependent",
                        "text": "A claim about the invalid event.",
                        "event_id": "evt-invalid",
                        "subject_ref": "ent-independent",
                    }
                ],
                "relationships": [
                    {
                        "relationship_id": "rel-dependent",
                        "subject_ref": "ent-independent",
                        "object_ref": "clm-dependent",
                        "source_relation_label": "announced",
                    }
                ],
            },
        )

    assert response.status_code == 201
    results = {item["local_id"]: item for item in response.json()["object_results"]}
    assert results["evt-invalid"]["errors"] == ["invalid temporal value"]
    assert results["clm-dependent"]["errors"] == [
        "event_id depends on rejected object: evt-invalid"
    ]
    assert results["rel-dependent"]["errors"] == [
        "object_ref depends on rejected object: clm-dependent"
    ]


def test_rejects_cross_type_local_id_collisions() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Ambiguous IDs", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [{"source_id": "src-1"}],
                "articles": [],
                "evidence": [],
                "entities": [{"entity_id": "shared", "type": "organization", "name": "Example Group"}],
                "events": [{"event_id": "shared", "type": "meeting", "title": "Example meeting"}],
                "claims": [],
            },
        )

    assert response.status_code == 201
    assert response.json()["summary"]["accepted"] == 1
    assert response.json()["summary"]["rejected"] == 2


def test_enforces_taxonomy_epistemic_status_and_temporal_order() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Controlled validation",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {
                        "entity_id": "ent-1",
                        "type": "nonprofit_collective",
                        "name": "Example Collective",
                    }
                ],
                "events": [
                    {
                        "event_id": "evt-invalid",
                        "type": "meeting",
                        "title": "Backwards event",
                        "temporal": {
                            "start": "2026-07-26T10:00:00Z",
                            "end": "2026-07-25T10:00:00Z",
                            "precision": "range",
                            "basis": "reported",
                        },
                    }
                ],
                "claims": [
                    {
                        "claim_id": "clm-invalid",
                        "text": "An invalid epistemic classification.",
                        "epistemic_status": "rumor",
                    }
                ],
                "relationships": [],
            },
        )

    assert response.status_code == 201
    results = {item["local_id"]: item for item in response.json()["object_results"]}
    assert results["ent-1"]["status"] == "accepted"
    assert results["evt-invalid"]["errors"] == ["invalid temporal value"]
    assert results["clm-invalid"]["errors"] == ["invalid epistemic_status"]

    with Session(get_engine()) as session:
        canonical = session.get(CanonicalEntity, uuid.UUID(results["ent-1"]["canonical_id"]))
        mention = session.scalar(
            select(EntityMention)
            .join(RawPackage, RawPackage.id == EntityMention.raw_package_id)
            .where(
                RawPackage.package_id == uuid.UUID(response.json()["package_id"]),
                EntityMention.local_id == "ent-1",
            )
        )
    assert canonical is not None and canonical.entity_type == "unknown"
    assert mention is not None and mention.source_type == "nonprofit_collective"


def test_rejects_duplicate_local_ids_and_accepts_zero_evidence_offset() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        payload = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "Validation delivery", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}, {"source_id": "src-1"}, {"source_id": "src-ok"}],
            "articles": [{"article_id": "art-1", "source_id": "src-ok", "content": "Evidence text"}],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "article_id": "art-1",
                    "excerpt": "Evidence",
                    "start_offset": 0,
                    "end_offset": 8,
                }
            ],
            "entities": [],
            "events": [],
            "claims": [],
        }
        response = client.post("/ingestions", json=payload)

    assert response.status_code == 201
    assert response.json()["summary"]["accepted"] == 3
    assert response.json()["summary"]["rejected"] == 2


def test_persists_accepted_mentions_with_their_package_provenance() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        package_id = str(uuid.uuid4())
        payload = {
            "schema_version": "1.0",
            "package_id": package_id,
            "topic_key": topic_key,
            "metadata": {"title": "Complete delivery", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [{"article_id": "art-1", "source_id": "src-1", "content": "Evidence text"}],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "article_id": "art-1",
                    "excerpt": "Evidence",
                    "start_offset": 0,
                    "end_offset": 8,
                }
            ],
            "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
            "events": [{"event_id": "evt-1", "type": "meeting", "title": "Example meeting"}],
            "claims": [
                {
                    "claim_id": "clm-1",
                    "text": "Example Group held a meeting.",
                    "event_id": "evt-1",
                    "subject_ref": "ent-1",
                    "predicate_candidate": "participated_in",
                    "object_ref_or_value": "evt-1",
                    "evidence_ids": ["ev-1"],
                }
            ],
            "relationships": [
                {
                    "relationship_id": "rel-1",
                    "subject_ref": "ent-1",
                    "object_ref": "evt-1",
                    "source_relation_label": "participated in",
                    "evidence_ids": ["ev-1"],
                }
            ],
        }
        response = client.post("/ingestions", json=payload)

    assert response.status_code == 201
    assert response.json()["summary"]["created"] == 4
    mapped_results = {
        item["local_type"]: item for item in response.json()["object_results"]
    }
    assert all(
        "canonical_id" in mapped_results[local_type]
        and "decision_id" in mapped_results[local_type]
        for local_type in {
            "source",
            "article",
            "evidence",
            "entity",
            "event",
            "claim",
            "relationship",
        }
    )
    with Session(get_engine()) as session:
        raw_package = session.scalar(select(RawPackage).where(RawPackage.package_id == package_id))
        assert raw_package is not None
        assert session.scalar(select(SourceMention).where(SourceMention.raw_package_id == raw_package.id))
        article = session.scalar(select(ArticleVersion).where(ArticleVersion.raw_package_id == raw_package.id))
        evidence = session.scalar(select(EvidenceMention).where(EvidenceMention.raw_package_id == raw_package.id))
        assert article is not None
        assert evidence is not None
        assert evidence.article_version_id == article.id
        assert session.scalar(select(EntityMention).where(EntityMention.raw_package_id == raw_package.id))
        assert session.scalar(select(EventMention).where(EventMention.raw_package_id == raw_package.id))
        assert session.scalar(select(ClaimMention).where(ClaimMention.raw_package_id == raw_package.id))
        assert session.scalar(select(RelationshipMention).where(RelationshipMention.raw_package_id == raw_package.id))
        assert session.scalar(select(CanonicalEntity))
        assert session.scalar(select(CanonicalEvent))
        assert session.scalar(select(Claim))
        claim_assertion = session.scalar(
            select(ClaimAssertion).where(
                ClaimAssertion.claim_id
                == uuid.UUID(mapped_results["claim"]["canonical_id"])
            )
        )
        assert claim_assertion is not None
        assert claim_assertion.derivation_method == "normalized_layer1_candidate"
        assert claim_assertion.input_ids
        assert claim_assertion.confidence == 0.8
        assert claim_assertion.processing_version == "kg-pipeline-0.2"
        assert claim_assertion.resolution_decision_id == uuid.UUID(
            mapped_results["claim"]["decision_id"]
        )
        claim_provenance = session.scalar(
            select(ProvenanceLink).where(
                ProvenanceLink.graph_object_type == "claim",
                ProvenanceLink.graph_object_id
                == uuid.UUID(mapped_results["claim"]["canonical_id"]),
                ProvenanceLink.evidence_mention_id == evidence.id,
            )
        )
        assert claim_provenance is not None
        assert claim_provenance.claim_id == uuid.UUID(
            mapped_results["claim"]["canonical_id"]
        )
        mappings = list(
            session.scalars(select(LocalIdMapping).where(LocalIdMapping.raw_package_id == raw_package.id))
        )
        assert {mapping.local_type for mapping in mappings} == {
            "source",
            "article",
            "evidence",
            "entity",
            "event",
            "claim",
            "relationship",
        }
        provenance_types = {
            link.graph_object_type
            for link in session.scalars(
                select(ProvenanceLink).where(ProvenanceLink.raw_package_id == raw_package.id)
            )
        }
        assert {
            "source",
            "article",
            "evidence",
            "entity",
            "event",
            "claim",
            "relationship",
        }.issubset(provenance_types)
        relationship = session.scalar(
            select(GraphRelationship).where(GraphRelationship.topic_id == raw_package.topic_id)
        )
        assert relationship is not None
        assert relationship.relationship_type == "PARTICIPATED_IN"
        relationship_assertion = session.scalar(
            select(RelationshipAssertion).where(RelationshipAssertion.relationship_id == relationship.id)
        )
        assert relationship_assertion is not None
        assert relationship_assertion.derivation_method == "normalized_source_relation"
        assert relationship_assertion.input_ids
        assert relationship_assertion.processing_version == "kg-pipeline-0.2"
        assert relationship_assertion.resolution_decision_id == uuid.UUID(
            mapped_results["relationship"]["decision_id"]
        )
        confidence = session.scalar(
            select(ConfidenceAssessment).where(
                ConfidenceAssessment.subject_type == "relationship",
                ConfidenceAssessment.subject_id == relationship.id,
            )
        )
        assert confidence is not None
        assert confidence.model_or_rule_version == "kg-pipeline-0.2"
        assert confidence.supporting_ids
        provenance = session.scalar(
            select(ProvenanceLink).where(ProvenanceLink.graph_object_id == relationship.id)
        )
        assert provenance is not None
        assert provenance.evidence_mention_id == evidence.id


def test_maps_an_unknown_relationship_to_a_retained_candidate() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        response = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Unknown relationship",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {"entity_id": "ent-a", "type": "organization", "name": "Alpha Group"},
                    {"entity_id": "ent-b", "type": "organization", "name": "Beta Group"},
                ],
                "events": [],
                "claims": [],
                "relationships": [
                    {
                        "relationship_id": "rel-unknown",
                        "subject_ref": "ent-a",
                        "object_ref": "ent-b",
                        "source_relation_label": "collaborated with",
                    }
                ],
            },
        )

    assert response.status_code == 201
    result = next(
        item for item in response.json()["object_results"] if item["local_type"] == "relationship"
    )
    assert result["classification"] == "retained_candidate"
    assert result["canonical_id"]
    assert result["decision_id"]

    with Session(get_engine()) as session:
        mapping = session.scalar(
            select(LocalIdMapping).where(
                LocalIdMapping.raw_package_id
                == session.scalar(
                    select(RawPackage.id).where(
                        RawPackage.package_id == uuid.UUID(response.json()["package_id"])
                    )
                ),
                LocalIdMapping.local_type == "relationship",
                LocalIdMapping.local_id == "rel-unknown",
            )
        )
        decision = session.get(ResolutionDecision, uuid.UUID(result["decision_id"]))
        canonical_edges = list(
            session.scalars(
                select(GraphRelationship).where(
                    GraphRelationship.topic_id == uuid.UUID(response.json()["topic_id"])
                )
            )
        )

    assert mapping is not None
    assert mapping.canonical_type == "relationship_candidate"
    assert decision is not None and decision.outcome == "CREATE_NEW"
    assert "outside the canonical ontology" in decision.rationale
    assert canonical_edges == []


def test_retains_article_version_lineage() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        url = f"https://example.test/{uuid.uuid4()}"
        for article_id, content in (
            ("art-1", "First article text"),
            ("art-2", "Corrected article text"),
            ("art-3", "Corrected article text"),
        ):
            response = client.post(
                "/ingestions",
                json={
                    "schema_version": "1.0",
                    "package_id": str(uuid.uuid4()),
                    "topic_key": topic_key,
                    "metadata": {"title": "Article update", "generated_at": "2026-07-25T10:30:00Z"},
                    "sources": [{"source_id": f"src-{article_id}"}],
                    "articles": [{"article_id": article_id, "source_id": f"src-{article_id}", "url": url, "content": content}],
                    "evidence": [],
                    "entities": [],
                    "events": [],
                    "claims": [],
                },
            )
            assert response.status_code == 201

    with Session(get_engine()) as session:
        versions = list(
            session.scalars(
                select(ArticleVersion)
                .where(ArticleVersion.canonical_url == url)
            )
        )
    assert len(versions) == 3
    versions_by_local_id = {version.local_id: version for version in versions}
    assert versions_by_local_id["art-2"].previous_version_id == versions_by_local_id["art-1"].id
    assert versions_by_local_id["art-2"].duplicate_of_id is None
    assert versions_by_local_id["art-3"].previous_version_id is None
    assert versions_by_local_id["art-3"].duplicate_of_id == versions_by_local_id["art-2"].id
    assert versions_by_local_id["art-1"].article_fingerprint


def test_as_of_context_excludes_later_claims_and_graph_expansion_rejects_cross_topic_seed() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0", "package_id": str(uuid.uuid4()), "topic_key": topic_key,
                "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [], "articles": [], "evidence": [], "entities": [], "events": [],
                "claims": [{"claim_id": "clm-1", "text": "First reported claim."}],
            },
        )
        second = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0", "package_id": str(uuid.uuid4()), "topic_key": topic_key,
                "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
                "sources": [], "articles": [], "evidence": [], "entities": [], "events": [],
                "claims": [{"claim_id": "clm-2", "text": "Later reported claim."}],
            },
        )
        assert first.status_code == second.status_code == 201

    with Session(get_engine()) as session:
        first_run = session.get(IngestionRun, uuid.UUID(first.json()["ingestion_id"]))
        assert first_run is not None
        as_of = first_run.completed_at.isoformat()

    with TestClient(app) as client:
        topic_id = first.json()["topic_id"]
        historical = client.get(f"/topics/{topic_id}/context", params={"as_of": as_of})
        other_topic_key = register_topic(client)
        other = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0", "package_id": str(uuid.uuid4()), "topic_key": other_topic_key,
                "metadata": {"title": "Other", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [], "articles": [], "evidence": [],
                "entities": [{"entity_id": "other-entity", "type": "organization", "name": "Other Group"}],
                "events": [], "claims": [],
            },
        )
        other_entity_id = next(
            item["canonical_id"] for item in other.json()["object_results"] if item["local_type"] == "entity"
        )
        cross_topic = client.post(
            "/graph/expand", json={"topic_id": topic_id, "seed_ids": [other_entity_id]}
        )

    assert historical.status_code == 200
    assert [claim["text"] for claim in historical.json()["claims"]] == ["First reported claim."]
    assert cross_topic.status_code == 400


def test_as_of_context_uses_historical_lifecycle_support_and_confidence() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)

        def ingest_entity(local_id: str):
            return client.post(
                "/ingestions",
                json={
                    "schema_version": "1.0",
                    "package_id": str(uuid.uuid4()),
                    "topic_key": topic_key,
                    "metadata": {
                        "title": local_id,
                        "generated_at": "2026-07-25T10:30:00Z",
                    },
                    "sources": [],
                    "articles": [],
                    "evidence": [],
                    "entities": [
                        {
                            "entity_id": local_id,
                            "type": "organization",
                            "name": "Historically Supported Group",
                        }
                    ],
                    "events": [],
                    "claims": [],
                },
            )

        first = ingest_entity("ent-first")
        second = ingest_entity("ent-second")
        topic_id = first.json()["topic_id"]
        closed = client.post(
            f"/topics/{topic_id}/lifecycle",
            json={"status": "closed", "reason": "Coverage complete."},
        )

    assert first.status_code == second.status_code == 201
    assert closed.status_code == 200
    with Session(get_engine()) as session:
        first_run = session.get(IngestionRun, uuid.UUID(first.json()["ingestion_id"]))
        assert first_run is not None
        as_of = first_run.completed_at.isoformat()

    with TestClient(app) as client:
        historical = client.get(f"/topics/{topic_id}/context", params={"as_of": as_of})
        current = client.get(f"/topics/{topic_id}/context")

    assert historical.status_code == current.status_code == 200
    historical_entity = historical.json()["entities"][0]
    current_entity = current.json()["entities"][0]
    assert historical.json()["topic"]["status"] == "active"
    assert historical_entity["support"]["package_count"] == 1
    assert historical_entity["confidence"] == [
        {
            "dimension": "entity_resolution",
            "value": 0.8,
            "method": "no_match_in_bounded_candidates",
        }
    ]
    assert current.json()["topic"]["status"] == "closed"
    assert current_entity["support"]["package_count"] == 2
    assert current_entity["confidence"][0]["value"] == 1.0


def test_as_of_context_uses_historical_relationship_status() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Historical relationship status",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {"entity_id": "ent-a", "type": "organization", "name": "Alpha Group"},
                    {"entity_id": "ent-b", "type": "organization", "name": "Beta Group"},
                ],
                "events": [],
                "claims": [],
                "relationships": [
                    {
                        "relationship_id": "rel-1",
                        "subject_ref": "ent-a",
                        "object_ref": "ent-b",
                        "source_relation_label": "responded to",
                    }
                ],
            },
        )

    assert ingestion.status_code == 201
    relationship_id = uuid.UUID(
        next(
            item["canonical_id"]
            for item in ingestion.json()["object_results"]
            if item["local_type"] == "relationship"
        )
    )
    with Session(get_engine()) as session:
        run = session.get(IngestionRun, uuid.UUID(ingestion.json()["ingestion_id"]))
        relationship = session.get(GraphRelationship, relationship_id)
        assert run is not None and relationship is not None
        as_of = run.completed_at.isoformat()
        relationship.status = "superseded"
        session.add(
            RelationshipStatusHistory(
                relationship_id=relationship.id,
                status="superseded",
                reason="Later resolution superseded the edge.",
            )
        )
        session.commit()

    with TestClient(app) as client:
        historical = client.get(
            f"/topics/{ingestion.json()['topic_id']}/context",
            params={"as_of": as_of},
        )
        current = client.get(f"/topics/{ingestion.json()['topic_id']}/context")

    assert historical.json()["relationships"][0]["status"] == "active"
    assert current.json()["relationships"][0]["status"] == "superseded"


def test_returns_a_structured_story_summary_with_actor_roles_and_interpretive_annotations() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Story context", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
                "events": [{"event_id": "evt-1", "type": "meeting", "title": "Example meeting"}],
                "claims": [{"claim_id": "clm-1", "text": "Example Group held a meeting.", "event_id": "evt-1"}],
                "relationships": [{"relationship_id": "rel-1", "subject_ref": "ent-1", "object_ref": "evt-1", "source_relation_label": "participated in"}],
                "themes": [{"label": "public activity"}],
                "sentiment": [{"label": "tense"}],
                "uncertainties": [{"text": "The reported attendance is unverified."}],
            },
        )
        assert ingestion.status_code == 201
        context = client.get(f"/topics/{ingestion.json()['topic_id']}/context")

    assert context.status_code == 200
    body = context.json()
    claim_id = next(item["canonical_id"] for item in ingestion.json()["object_results"] if item["local_type"] == "claim")
    entity_id = next(item["canonical_id"] for item in ingestion.json()["object_results"] if item["local_type"] == "entity")
    assert body["summary"] == {
        "text": "Example Group held a meeting.",
        "claim_ids": [claim_id],
        "claims": [{"claim_id": claim_id, "text": "Example Group held a meeting.", "status": "active"}],
    }
    assert body["actors"] == [{"entity_id": entity_id, "label": "Example Group", "roles": ["PARTICIPATED_IN"]}]
    assert body["themes"] == [{"label": "public activity", "interpretive": True}]
    assert body["sentiment"] == [{"label": "tense", "interpretive": True}]
    assert body["interpretations"] == [
        {"interpretation_id": "themes:0", "text": "public activity", "labelled": "interpretive"},
        {"interpretation_id": "sentiment:0", "text": "tense", "labelled": "interpretive"},
    ]
    assert body["uncertainties"] == [{"text": "The reported attendance is unverified.", "status": "uncertain"}]


def test_serializes_concurrent_same_topic_entity_ingestion() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)

    def ingest(local_id: str) -> int:
        with TestClient(app) as client:
            return client.post(
                "/ingestions",
                json={
                    "schema_version": "1.0", "package_id": str(uuid.uuid4()), "topic_key": topic_key,
                    "metadata": {"title": "Concurrent delivery", "generated_at": "2026-07-25T10:30:00Z"},
                    "sources": [], "articles": [], "evidence": [],
                    "entities": [{"entity_id": local_id, "type": "organization", "name": "Example Group"}],
                    "events": [], "claims": [],
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(ingest, ["ent-1", "ent-2"]))

    assert statuses == [201, 201]
    with Session(get_engine()) as session:
        topic_id = session.scalar(select(Topic.id).where(Topic.topic_key == topic_key))
        canonical_ids = set(
            session.scalars(
                select(LocalIdMapping.canonical_id)
                .join(RawPackage, LocalIdMapping.raw_package_id == RawPackage.id)
                .where(
                    RawPackage.topic_id == topic_id,
                    LocalIdMapping.local_type == "entity",
                )
            )
        )
    assert len(canonical_ids) == 1


def test_reconciles_relationships_and_aggregates_independent_assertions() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)

        def ingest_relationship(suffix: str, start: str = "2026-07-25T10:00:00Z"):
            return client.post(
                "/ingestions",
                json={
                    "schema_version": "1.0",
                    "package_id": str(uuid.uuid4()),
                    "topic_key": topic_key,
                    "metadata": {
                        "title": f"Relationship delivery {suffix}",
                        "generated_at": "2026-07-25T10:30:00Z",
                    },
                    "sources": [],
                    "articles": [],
                    "evidence": [],
                    "entities": [
                        {
                            "entity_id": f"ent-alpha-{suffix}",
                            "type": "organization",
                            "name": "Alpha Group",
                        },
                        {
                            "entity_id": f"ent-beta-{suffix}",
                            "type": "organization",
                            "name": "Beta Group",
                        },
                    ],
                    "events": [],
                    "claims": [],
                    "relationships": [
                        {
                            "relationship_id": f"rel-{suffix}",
                            "subject_ref": f"ent-alpha-{suffix}",
                            "object_ref": f"ent-beta-{suffix}",
                            "source_relation_label": "responded to",
                            "temporal_scope": {
                                "start": start,
                                "precision": "minute",
                                "basis": "reported",
                            },
                        }
                    ],
                },
            )

        first = ingest_relationship("one")
        second = ingest_relationship("two")
        later = ingest_relationship("later", start="2026-07-26T10:00:00Z")

    assert first.status_code == second.status_code == later.status_code == 201
    first_result = next(
        item for item in first.json()["object_results"] if item["local_type"] == "relationship"
    )
    second_result = next(
        item for item in second.json()["object_results"] if item["local_type"] == "relationship"
    )
    later_result = next(
        item for item in later.json()["object_results"] if item["local_type"] == "relationship"
    )
    assert second_result["canonical_id"] == first_result["canonical_id"]
    assert second_result["classification"] == "confirmation"
    assert later_result["canonical_id"] != first_result["canonical_id"]
    assert later_result["classification"] == "new"

    with Session(get_engine()) as session:
        relationships = list(
            session.scalars(
                select(GraphRelationship).where(
                    GraphRelationship.topic_id == uuid.UUID(first.json()["topic_id"]),
                    GraphRelationship.relationship_type == "RESPONDED_TO",
                )
            )
        )
        assertions = list(
            session.scalars(
                select(RelationshipAssertion).where(
                    RelationshipAssertion.relationship_id
                    == uuid.UUID(first_result["canonical_id"])
                )
            )
        )

    assert len(relationships) == 2
    assert len(assertions) == 2


def test_resolves_an_exact_entity_match_within_a_topic() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
            "events": [],
            "claims": [],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "entities": [{"entity_id": "ent-2", "type": "organization", "name": "  example   group "}],
        }
        first_response = client.post("/ingestions", json=first)
        second_response = client.post("/ingestions", json=second)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first_entity = next(
        result for result in first_response.json()["object_results"] if result["local_type"] == "entity"
    )
    second_entity = next(
        result for result in second_response.json()["object_results"] if result["local_type"] == "entity"
    )
    assert second_response.json()["summary"]["created"] == 0
    assert second_response.json()["summary"]["matched"] == 1
    assert second_entity["classification"] == "matched"
    assert second_entity["canonical_id"] == first_entity["canonical_id"]
    with Session(get_engine()) as session:
        decision = session.get(ResolutionDecision, uuid.UUID(second_entity["decision_id"]))
        assert decision is not None
        assert decision.input_schema_version == "1.0"
        assert decision.graph_model_version == "kg-model-0.1"
        assert decision.processing_version == "kg-pipeline-0.2"
        assert decision.ontology_version == "kg-ontology-0.2"
        assert decision.signals_json["selected_canonical_id"] == second_entity["canonical_id"]
        assert decision.signals_json["candidates"] == [
            {"canonical_id": second_entity["canonical_id"], "score": 1.0}
        ]
        confidence = list(
            session.scalars(
                select(ConfidenceAssessment).where(
                    ConfidenceAssessment.subject_type == "entity",
                    ConfidenceAssessment.subject_id == uuid.UUID(second_entity["canonical_id"]),
                    ConfidenceAssessment.dimension == "entity_resolution",
                )
            )
        )
        assert any(assessment.value == 1.0 for assessment in confidence)
        topic_id = session.scalar(
            select(RawPackage.topic_id).where(RawPackage.package_id == uuid.UUID(second["package_id"]))
        )

    with TestClient(app) as client:
        context = client.get(f"/topics/{topic_id}/context")

    assert context.status_code == 200
    entity = next(item for item in context.json()["entities"] if item["entity_id"] == second_entity["canonical_id"])
    assert entity["confidence"] == [
        {"dimension": "entity_resolution", "value": 1.0, "method": "deterministic_exact_match"}
    ]
    assert entity["support"] == {"package_count": 2, "assessment": "corroborated"}


def test_resolves_exact_entity_matches_beyond_the_candidate_window() -> None:
    names = [f"Bureau Of Example Affairs {index}" for index in range(CANDIDATE_LIMIT + 5)]
    shared = {
        "schema_version": "1.0",
        "sources": [{"source_id": "src-1"}],
        "articles": [],
        "evidence": [],
        "events": [],
        "claims": [],
    }
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first_response = client.post(
            "/ingestions",
            json={
                **shared,
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
                "entities": [
                    {"entity_id": f"ent-a-{index}", "type": "organization", "name": name}
                    for index, name in enumerate(names)
                ],
            },
        )
        second_response = client.post(
            "/ingestions",
            json={
                **shared,
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
                "entities": [
                    {"entity_id": f"ent-b-{index}", "type": "organization", "name": name}
                    for index, name in enumerate(names)
                ],
            },
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["summary"]["created"] == len(names)
    assert second_response.json()["summary"]["created"] == 0
    assert second_response.json()["summary"]["matched"] == len(names)


def test_resolves_an_entity_by_a_preserved_alias() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Full name", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {
                        "entity_id": "ent-full",
                        "type": "government_agency",
                        "name": "National Disaster Response Force",
                        "aliases": ["NDRF"],
                    }
                ],
                "events": [],
                "claims": [],
            },
        )
        second = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Alias", "generated_at": "2026-07-25T11:30:00Z"},
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {
                        "entity_id": "ent-alias",
                        "type": "government_agency",
                        "name": "ＮＤＲＦ",
                    }
                ],
                "events": [],
                "claims": [],
            },
        )

    first_entity = next(
        item for item in first.json()["object_results"] if item["local_type"] == "entity"
    )
    second_entity = next(
        item for item in second.json()["object_results"] if item["local_type"] == "entity"
    )
    assert second_entity["classification"] == "matched"
    assert second_entity["canonical_id"] == first_entity["canonical_id"]


def test_resolves_an_event_only_with_matching_time_and_participant() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
            "events": [
                {
                    "event_id": "evt-1",
                    "type": "meeting",
                    "title": "Example meeting",
                    "temporal": {"start": "2026-07-20T10:00:00Z", "precision": "exact", "basis": "reported"},
                    "participant_entity_ids": ["ent-1"],
                }
            ],
            "claims": [],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "entities": [{"entity_id": "ent-2", "type": "organization", "name": "example group"}],
            "events": [
                {
                    **first["events"][0],
                    "event_id": "evt-2",
                    "participant_entity_ids": ["ent-2"],
                }
            ],
        }
        first_response = client.post("/ingestions", json=first)
        second_response = client.post("/ingestions", json=second)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first_event = next(
        result for result in first_response.json()["object_results"] if result["local_type"] == "event"
    )
    second_event = next(
        result for result in second_response.json()["object_results"] if result["local_type"] == "event"
    )
    assert second_event["classification"] == "matched"
    assert second_event["canonical_id"] == first_event["canonical_id"]
    with Session(get_engine()) as session:
        assert session.get(EventResolutionContext, uuid.UUID(first_event["canonical_id"]))


def test_promotes_structured_claims_to_a_confirmed_contradiction() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
            "events": [],
            "claims": [
                {
                    "claim_id": "clm-1",
                    "text": "Example Group is operational.",
                    "subject_ref": "ent-1",
                    "predicate_candidate": "operational_status",
                    "object_ref_or_value": "operational",
                    "temporal_scope": {"start": "2026-07-20", "precision": "day", "basis": "reported"},
                }
            ],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "entities": [{"entity_id": "ent-2", "type": "organization", "name": "example group"}],
            "claims": [
                {
                    **first["claims"][0],
                    "claim_id": "clm-2",
                    "text": "Example Group is not operational.",
                    "subject_ref": "ent-2",
                    "object_ref_or_value": "not_operational",
                    "epistemic_status": "disputed",
                }
            ],
        }
        first_response = client.post("/ingestions", json=first)
        second_response = client.post("/ingestions", json=second)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    claim_result = next(
        result for result in second_response.json()["object_results"] if result["local_type"] == "claim"
    )
    assert claim_result["classification"] == "confirmed_contradiction"
    assert second_response.json()["summary"]["contradictions"] == 1
    with Session(get_engine()) as session:
        decision = session.get(
            ResolutionDecision, uuid.UUID(claim_result["decision_id"])
        )
        assert decision is not None
        assert decision.outcome == "CREATE_CONFIRMED_CONTRADICTION"
        assert decision.signals_json["candidates"][0]["score"] == 1.0
        assertions = list(session.scalars(select(ClaimAssertion)))
        assert len(assertions) >= 2
        relationship = session.scalar(
            select(GraphRelationship).where(
                GraphRelationship.relationship_type == "CONTRADICTS",
                GraphRelationship.status == "confirmed_contradiction",
            )
        )
        assert relationship is not None
        assertion_statuses = list(
            session.scalars(
                select(RelationshipAssertion.status).where(
                    RelationshipAssertion.relationship_id == relationship.id
                )
            )
        )
        assert assertion_statuses == ["possible_contradiction", "confirmed_contradiction"]

    with TestClient(app) as client:
        filtered = client.get(
            f"/topics/{first_response.json()['topic_id']}/context",
            params={"include_disputed": False},
        )

    assert all(
        claim["epistemic_status"] != "disputed"
        for claim in filtered.json()["claims"]
    )
    assert all(
        relationship["type"] != "CONTRADICTS"
        for relationship in filtered.json()["relationships"]
    )


def test_only_contradicts_quantities_with_compatible_units_and_scopes() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First count", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [],
            "articles": [],
            "evidence": [],
            "entities": [
                {"entity_id": "ent-1", "type": "organization", "name": "Example Group"}
            ],
            "events": [],
            "claims": [
                {
                    "claim_id": "clm-1",
                    "text": "Five hundred residents were displaced.",
                    "subject_ref": "ent-1",
                    "predicate_candidate": "displaced_count",
                    "object_ref_or_value": {
                        "type": "quantity",
                        "original_text": "500 residents",
                        "value": 500,
                        "unit": "people",
                        "population": "displaced residents",
                        "measurement_scope": "individual people",
                    },
                    "temporal_scope": {
                        "start": "2026-07-20",
                        "precision": "day",
                        "basis": "reported",
                    },
                }
            ],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {
                "title": "Second count",
                "generated_at": "2026-07-25T11:30:00Z",
            },
            "entities": [
                {"entity_id": "ent-2", "type": "organization", "name": "Example Group"}
            ],
            "claims": [
                {
                    **first["claims"][0],
                    "claim_id": "clm-2",
                    "text": "One thousand families were displaced.",
                    "subject_ref": "ent-2",
                    "object_ref_or_value": {
                        "type": "quantity",
                        "original_text": "1,000 families",
                        "value": 1000,
                        "unit": "families",
                        "population": "displaced households",
                        "measurement_scope": "family units",
                    },
                }
            ],
        }

        first_response = client.post("/ingestions", json=first)
        second_response = client.post("/ingestions", json=second)
        third = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {
                "title": "Comparable count",
                "generated_at": "2026-07-25T12:30:00Z",
            },
            "entities": [
                {"entity_id": "ent-3", "type": "organization", "name": "Example Group"}
            ],
            "claims": [
                {
                    **first["claims"][0],
                    "claim_id": "clm-3",
                    "text": "One thousand residents were displaced.",
                    "subject_ref": "ent-3",
                    "object_ref_or_value": {
                        "type": "quantity",
                        "original_text": "1,000 residents",
                        "value": 1000,
                        "unit": " People ",
                        "population": "Displaced Residents",
                        "measurement_scope": "Individual People",
                    },
                }
            ],
        }
        third_response = client.post("/ingestions", json=third)

    assert first_response.status_code == second_response.status_code == third_response.status_code == 201
    second_claim = next(
        item for item in second_response.json()["object_results"] if item["local_type"] == "claim"
    )
    third_claim = next(
        item for item in third_response.json()["object_results"] if item["local_type"] == "claim"
    )
    assert second_claim["classification"] == "new"
    assert third_claim["classification"] == "confirmed_contradiction"
    with Session(get_engine()) as session:
        contradictions = list(
            session.scalars(
                select(GraphRelationship).where(
                    GraphRelationship.topic_id == uuid.UUID(first_response.json()["topic_id"]),
                    GraphRelationship.relationship_type == "CONTRADICTS",
                )
            )
        )
    assert len(contradictions) == 1


def test_filters_an_open_ended_event_by_time_without_failing() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Open ended", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [{"source_id": "src-1"}],
                "articles": [],
                "evidence": [],
                "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
                "events": [
                    {
                        "event_id": "evt-ongoing",
                        "type": "meeting",
                        "title": "Ongoing inquiry",
                        "temporal": {
                            "start": "2026-07-20T10:00:00Z",
                            "end": None,
                            "precision": "exact",
                            "basis": "reported",
                        },
                        "participant_entity_ids": ["ent-1"],
                    }
                ],
                "claims": [],
            },
        )
        topic_id = ingestion.json()["topic_id"]
        context = client.get(
            f"/topics/{topic_id}/context", params={"time_start": "2026-07-01T00:00:00Z"}
        )

    assert ingestion.status_code == 201
    assert context.status_code == 200
    assert [event["temporal"]["start"] for event in context.json()["events"]] == [
        "2026-07-20T10:00:00Z"
    ]


def test_returns_redacted_topic_context_and_event_time_timeline() -> None:
    with TestClient(app) as client:
        topic_key = f"context-topic-{uuid.uuid4().hex}"
        topic_response = client.post(
            "/topics",
            json={
                "topic_key": topic_key,
                "display_name": "Context topic",
                "scope": {"description": "A test topic.", "geography": [], "start": "2026-07-01"},
            },
        )
        topic_id = topic_response.json()["topic_id"]
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Context input", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [{"source_id": "src-private"}],
                "articles": [],
                "evidence": [],
                "entities": [{"entity_id": "ent-private", "type": "organization", "name": "Example Group"}],
                "events": [
                    {
                        "event_id": "evt-private",
                        "type": "meeting",
                        "title": "Example meeting",
                        "temporal": {"start": "2026-07-20T10:00:00Z", "precision": "exact", "basis": "reported"},
                        "participant_entity_ids": ["ent-private"],
                    }
                ],
                "claims": [{"claim_id": "clm-private", "text": "Example Group met."}],
            },
        )
        context = client.get(f"/topics/{topic_id}/context")
        bounded_context = client.get(f"/topics/{topic_id}/context?max_nodes=1")
        timeline = client.get(f"/topics/{topic_id}/timeline")

    assert ingestion.status_code == 201
    assert context.status_code == 200
    assert timeline.status_code == 200
    assert context.json()["topic"]["topic_id"] == topic_id
    assert context.json()["entities"][0]["label"] == "Example Group"
    assert timeline.json()["timeline"][0]["temporal"]["start"] == "2026-07-20T10:00:00Z"
    assert "src-private" not in context.text
    assert "ent-private" not in context.text
    assert "package_id" not in context.text
    bounded = bounded_context.json()
    assert bounded["coverage"]["returned_nodes"] == 1
    assert len(bounded["entities"]) + len(bounded["events"]) + len(bounded["claims"]) == 1
    cursor = bounded["coverage"]["next_cursor"]
    assert cursor is not None
    next_page = client.get(f"/topics/{topic_id}/context?max_nodes=1&cursor={cursor}")
    assert next_page.status_code == 200
    assert next_page.json()["coverage"]["returned_nodes"] == 1


def test_applies_time_range_to_events_claims_and_relationships() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {
                    "title": "Time-scoped graph",
                    "generated_at": "2026-07-25T10:30:00Z",
                },
                "sources": [],
                "articles": [],
                "evidence": [],
                "entities": [
                    {"entity_id": "ent-1", "type": "organization", "name": "Example Group"}
                ],
                "events": [
                    {
                        "event_id": "evt-inside",
                        "type": "meeting",
                        "title": "Inside event",
                        "temporal": {
                            "start": "2026-07-20T10:00:00Z",
                            "precision": "exact",
                            "basis": "reported",
                        },
                    }
                ],
                "claims": [
                    {
                        "claim_id": "clm-inside",
                        "text": "Inside claim.",
                        "temporal_scope": {
                            "start": "2026-07-20T11:00:00Z",
                            "precision": "exact",
                            "basis": "reported",
                        },
                    },
                    {
                        "claim_id": "clm-outside",
                        "text": "Outside claim.",
                        "temporal_scope": {
                            "start": "2026-07-23T11:00:00Z",
                            "precision": "exact",
                            "basis": "reported",
                        },
                    },
                ],
                "relationships": [
                    {
                        "relationship_id": "rel-inside",
                        "subject_ref": "ent-1",
                        "object_ref": "evt-inside",
                        "source_relation_label": "participated in",
                        "temporal_scope": {
                            "start": "2026-07-20T10:00:00Z",
                            "precision": "exact",
                            "basis": "reported",
                        },
                    },
                    {
                        "relationship_id": "rel-outside",
                        "subject_ref": "ent-1",
                        "object_ref": "clm-outside",
                        "source_relation_label": "announced",
                        "temporal_scope": {
                            "start": "2026-07-23T10:00:00Z",
                            "precision": "exact",
                            "basis": "reported",
                        },
                    },
                ],
            },
        )
        context = client.get(
            f"/topics/{ingestion.json()['topic_id']}/context",
            params={
                "time_start": "2026-07-20T00:00:00Z",
                "time_end": "2026-07-20T23:59:59Z",
            },
        )

    assert context.status_code == 200
    assert [event["title"] for event in context.json()["events"]] == ["Inside event"]
    assert [claim["text"] for claim in context.json()["claims"]] == ["Inside claim."]
    assert [relationship["type"] for relationship in context.json()["relationships"]] == [
        "PARTICIPATED_IN"
    ]


def test_expands_a_topic_graph_and_exports_redacted_raw_wording() -> None:
    with TestClient(app) as client:
        topic_key = f"expand-topic-{uuid.uuid4().hex}"
        topic_id = client.post(
            "/topics",
            json={
                "topic_key": topic_key,
                "display_name": "Expansion topic",
                "scope": {"description": "A test topic.", "geography": [], "start": "2026-07-01"},
            },
        ).json()["topic_id"]
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic_key,
                "metadata": {"title": "Expansion input", "generated_at": "2026-07-25T10:30:00Z"},
                "sources": [{"source_id": "src-private"}],
                "articles": [{"article_id": "art-private", "source_id": "src-private", "content": "Evidence text"}],
                "evidence": [{"evidence_id": "ev-private", "article_id": "art-private", "excerpt": "Evidence", "start_offset": 0, "end_offset": 8}],
                "entities": [{"entity_id": "ent-private", "type": "organization", "name": "Example Group"}],
                "events": [{"event_id": "evt-private", "type": "meeting", "title": "Example meeting"}],
                "claims": [{"claim_id": "clm-private", "text": "Example Group met.", "evidence_ids": ["ev-private"]}],
                "relationships": [{"relationship_id": "rel-private", "subject_ref": "ent-private", "object_ref": "evt-private", "source_relation_label": "participated in", "evidence_ids": ["ev-private"]}],
            },
        )
        entity_id = next(
            result["canonical_id"]
            for result in ingestion.json()["object_results"]
            if result["local_type"] == "entity"
        )
        claim_id = next(
            result["canonical_id"]
            for result in ingestion.json()["object_results"]
            if result["local_type"] == "claim"
        )
        expansion = client.post(
            "/graph/expand",
            json={
                "topic_id": topic_id,
                "seed_ids": [entity_id],
                "max_depth": 1,
                "max_nodes": 10,
                "max_relationships": 1,
            },
        )
        context = client.get(f"/topics/{topic_id}/context")
        export = client.get(f"/topics/{topic_id}/raw-export?status=active")
        filtered_export = client.get(f"/topics/{topic_id}/raw-export?claim_id={claim_id}")
        claim_evidence = client.get(f"/claims/{claim_id}/evidence")
        entity_context = client.get(f"/entities/{entity_id}/context?topic_id={topic_id}")
        report = client.get(f"/ingestions/{ingestion.json()['ingestion_id']}")

    assert ingestion.status_code == 201
    assert expansion.status_code == 200
    assert len(expansion.json()["relationships"]) == 1
    assert all(
        node["node_type"] in {"entity", "event", "claim"}
        and set(node) != {"id"}
        for node in expansion.json()["nodes"]
    )
    assert expansion.json()["coverage"]["returned_relationships"] == 1
    assert context.json()["query_hints"]["available_expansions"]
    assert context.json()["relationships"][0]["support"]["package_count"] == 1
    assert context.json()["relationships"][0]["confidence"]
    assert export.status_code == 200
    assert export.json()["items"] == [
        {
            "claim_id": claim_id,
            "status": "active",
            "event_id": None,
            "temporal": {},
            "raw_text": "Example Group met.",
            "evidence": [{"excerpt": "Evidence"}],
            "support": {"package_count": 1, "assessment": "single_package"},
        }
    ]
    assert export.json()["active"] == export.json()["items"]
    assert export.json()["disputed"] == []
    assert export.json()["superseded"] == []
    assert export.json()["retracted"] == []
    assert filtered_export.status_code == 200
    assert filtered_export.json()["items"] == export.json()["items"]
    assert "src-private" not in export.text
    assert "art-private" not in export.text
    assert "package_id" not in export.text
    invalid_cursor = client.get(f"/topics/{topic_id}/raw-export?cursor=not-a-cursor")
    assert invalid_cursor.status_code == 400
    assert entity_context.status_code == 200
    assert entity_context.json()["entity"]["entity_id"] == entity_id
    assert entity_context.json()["relationships"][0]["type"] == "PARTICIPATED_IN"
    assert claim_evidence.status_code == 200
    assert claim_evidence.json()["evidence"] == [{"excerpt": "Evidence"}]
    assert "src-private" not in claim_evidence.text
    assert report.status_code == 200
    assert report.json()["ingestion_id"] == ingestion.json()["ingestion_id"]
    assert report.json()["received_delta"]["claims"][0]["text"] == "Example Group met."
    assert report.json()["report"]["summary"]["created"] == 4
    assert report.json()["resolution_decisions"]
    assert {
        "rationale",
        "signals",
        "input_schema_version",
        "graph_model_version",
        "processing_version",
        "ontology_version",
        "supersedes_decision_id",
    } <= report.json()["resolution_decisions"][0].keys()


def test_retains_an_ambiguous_entity_as_a_possible_match() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Community Group"}],
            "events": [],
            "claims": [],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "entities": [{"entity_id": "ent-2", "type": "organization", "name": "Example Community Group International"}],
        }
        first_response = client.post("/ingestions", json=first)
        second_response = client.post("/ingestions", json=second)

    first_entity = next(
        result for result in first_response.json()["object_results"] if result["local_type"] == "entity"
    )
    second_entity = next(
        result for result in second_response.json()["object_results"] if result["local_type"] == "entity"
    )
    assert first_entity["canonical_id"] != second_entity["canonical_id"]
    assert second_entity["classification"] == "possible_match"
    with Session(get_engine()) as session:
        relationship = session.scalar(
            select(GraphRelationship).where(
                GraphRelationship.relationship_type == "POSSIBLY_SAME_AS",
                GraphRelationship.status == "possible_match",
                GraphRelationship.subject_id == uuid.UUID(second_entity["canonical_id"]),
            )
        )
        assessment = session.scalar(
            select(ConfidenceAssessment).where(
                ConfidenceAssessment.subject_id == uuid.UUID(second_entity["canonical_id"]),
                ConfidenceAssessment.dimension == "entity_resolution",
            )
        )
        assert relationship is not None
        assert assessment is not None
        assert assessment.value == 3 / 4
        decision = session.scalar(
            select(ResolutionDecision)
            .join(LocalIdMapping, LocalIdMapping.decision_id == ResolutionDecision.id)
            .where(
                LocalIdMapping.canonical_id == uuid.UUID(second_entity["canonical_id"]),
                LocalIdMapping.local_id == "ent-2",
            )
        )
        assert decision is not None
        assert decision.signals_json["candidate_policy_version"] == "bounded-v2"
        assert decision.signals_json["candidate_limit"] == 10


def test_retains_an_underspecified_event_as_a_possible_match() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [],
            "events": [{"event_id": "evt-1", "type": "meeting", "title": "Example meeting", "temporal": {"start": "2026-07-20T10:00:00Z", "precision": "exact", "basis": "reported"}}],
            "claims": [],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "events": [{**first["events"][0], "event_id": "evt-2"}],
        }
        first_response = client.post("/ingestions", json=first)
        second_response = client.post("/ingestions", json=second)

    first_event = next(
        result for result in first_response.json()["object_results"] if result["local_type"] == "event"
    )
    second_event = next(
        result for result in second_response.json()["object_results"] if result["local_type"] == "event"
    )
    assert first_event["canonical_id"] != second_event["canonical_id"]
    assert second_event["classification"] == "possible_match"


def test_classifies_later_structured_state_as_progression_not_contradiction() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        first = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "First", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [{"entity_id": "ent-1", "type": "organization", "name": "Example Group"}],
            "events": [],
            "claims": [{"claim_id": "clm-1", "text": "The group was operational.", "subject_ref": "ent-1", "predicate_candidate": "operational_status", "object_ref_or_value": "operational", "temporal_scope": {"start": "2026-07-20", "precision": "day", "basis": "reported"}}],
        }
        second = {
            **first,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Second", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "entities": [{"entity_id": "ent-2", "type": "organization", "name": "example group"}],
            "claims": [{"claim_id": "clm-2", "text": "The group was inactive.", "subject_ref": "ent-2", "predicate_candidate": "operational_status", "object_ref_or_value": "inactive", "temporal_scope": {"start": "2026-07-21", "precision": "day", "basis": "reported"}}],
        }
        client.post("/ingestions", json=first)
        response = client.post("/ingestions", json=second)

    claim = next(result for result in response.json()["object_results"] if result["local_type"] == "claim")
    assert claim["classification"] == "progression"
    assert response.json()["summary"]["contradictions"] == 0
    with Session(get_engine()) as session:
        assert session.scalar(select(GraphRelationship).where(GraphRelationship.relationship_type == "FOLLOWS"))


def test_links_an_explicit_correction_to_a_repeated_target_claim() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        initial = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "Initial", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [],
            "events": [],
            "claims": [{"claim_id": "clm-original", "text": "The original claim."}],
        }
        correction = {
            **initial,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Correction", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "claims": [
                {"claim_id": "clm-target", "text": "The original claim."},
                {"claim_id": "clm-correction", "text": "The corrected claim.", "corrects_claim_ref": "clm-target"},
            ],
        }
        initial_response = client.post("/ingestions", json=initial)
        correction_response = client.post("/ingestions", json=correction)

    assert initial_response.status_code == 201
    assert correction_response.status_code == 201
    corrected = next(
        result
        for result in correction_response.json()["object_results"]
        if result["local_id"] == "clm-correction"
    )
    assert corrected["classification"] == "correction"
    original = next(
        result
        for result in initial_response.json()["object_results"]
        if result["local_type"] == "claim"
    )
    with Session(get_engine()) as session:
        assert session.get(Claim, uuid.UUID(original["canonical_id"])).status == "superseded"
        assert session.scalar(select(GraphRelationship).where(GraphRelationship.relationship_type == "CORRECTS"))
        statuses = list(
            session.scalars(
                select(ClaimStatusHistory.status).where(
                    ClaimStatusHistory.claim_id == uuid.UUID(original["canonical_id"])
                )
            )
        )
        assert statuses == ["active", "superseded"]


def test_links_an_explicit_retraction_to_a_repeated_target_claim() -> None:
    with TestClient(app) as client:
        topic_key = register_topic(client)
        initial = {
            "schema_version": "1.0",
            "package_id": str(uuid.uuid4()),
            "topic_key": topic_key,
            "metadata": {"title": "Initial", "generated_at": "2026-07-25T10:30:00Z"},
            "sources": [{"source_id": "src-1"}],
            "articles": [],
            "evidence": [],
            "entities": [],
            "events": [],
            "claims": [{"claim_id": "clm-original", "text": "The original claim."}],
        }
        retraction = {
            **initial,
            "package_id": str(uuid.uuid4()),
            "metadata": {"title": "Retraction", "generated_at": "2026-07-25T11:30:00Z"},
            "sources": [{"source_id": "src-2"}],
            "claims": [
                {"claim_id": "clm-target", "text": "The original claim."},
                {"claim_id": "clm-retraction", "text": "The claim was retracted.", "retracts_claim_ref": "clm-target"},
            ],
        }
        initial_response = client.post("/ingestions", json=initial)
        retraction_response = client.post("/ingestions", json=retraction)

    retracted = next(
        result
        for result in retraction_response.json()["object_results"]
        if result["local_id"] == "clm-retraction"
    )
    assert retracted["classification"] == "retraction"
    original = next(
        result
        for result in initial_response.json()["object_results"]
        if result["local_type"] == "claim"
    )
    with Session(get_engine()) as session:
        assert session.get(Claim, uuid.UUID(original["canonical_id"])).status == "retracted"
        assert session.scalar(select(GraphRelationship).where(GraphRelationship.relationship_type == "RETRACTS"))
