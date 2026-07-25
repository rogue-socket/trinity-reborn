import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import app
from app.models import LocalIdMapping, MappingRevision, RawPackage, ResolutionDecision
from app.services.reconciliation import current_mapping_target, reverse_mapping


def test_reverses_a_mapping_without_rewriting_its_history() -> None:
    topic_key = f"mapping-reversal-{uuid.uuid4().hex}"
    with TestClient(app) as client:
        topic = client.post(
            "/topics",
            json={
                "topic_key": topic_key,
                "display_name": "Mapping reversal",
                "scope": {
                    "description": "A bounded mapping reversal test.",
                    "geography": [],
                    "start": "2026-07-01",
                },
            },
        )
        ingestion = client.post(
            "/ingestions",
            json={
                "schema_version": "1.0",
                "package_id": str(uuid.uuid4()),
                "topic_key": topic.json()["topic_key"],
                "metadata": {
                    "title": "Two distinct entities",
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
            },
        )

    assert ingestion.status_code == 201
    with Session(get_engine()) as session:
        raw_package_id = session.scalar(
            select(RawPackage.id).where(
                RawPackage.package_id == uuid.UUID(ingestion.json()["package_id"])
            )
        )
        mappings = {
            mapping.local_id: mapping
            for mapping in session.scalars(
                select(LocalIdMapping).where(
                    LocalIdMapping.raw_package_id == raw_package_id,
                    LocalIdMapping.local_type == "entity",
                )
            )
        }
        original_target = mappings["ent-a"].canonical_id
        replacement_target = mappings["ent-b"].canonical_id
        initial_decision = session.get(
            ResolutionDecision, mappings["ent-a"].decision_id
        )
        assert initial_decision is not None
        as_of = initial_decision.created_at

        reversal = reverse_mapping(
            session,
            mapping_id=mappings["ent-a"].id,
            canonical_type="entity",
            canonical_id=replacement_target,
            rationale="Operator evidence showed the original merge target was incorrect.",
        )
        session.commit()

        revisions = list(
            session.scalars(
                select(MappingRevision)
                .where(MappingRevision.mapping_id == mappings["ent-a"].id)
                .order_by(MappingRevision.created_at, MappingRevision.id)
            )
        )
        session.refresh(mappings["ent-a"])

        assert mappings["ent-a"].canonical_id == original_target
        assert current_mapping_target(session, mappings["ent-a"].id).canonical_id == replacement_target
        assert current_mapping_target(
            session, mappings["ent-a"].id, as_of=as_of
        ).canonical_id == original_target
        assert len(revisions) == 2
        assert revisions[1].supersedes_revision_id == revisions[0].id
        assert reversal.supersedes_decision_id == initial_decision.id

    with TestClient(app) as client:
        current = client.get(f"/topics/{topic.json()['topic_id']}/context")
        historical = client.get(
            f"/topics/{topic.json()['topic_id']}/context",
            params={"as_of": as_of.isoformat()},
        )

    assert [entity["label"] for entity in current.json()["entities"]] == ["Beta Group"]
    assert {entity["label"] for entity in historical.json()["entities"]} == {
        "Alpha Group",
        "Beta Group",
    }
