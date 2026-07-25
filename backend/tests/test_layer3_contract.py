"""Layer 3 reads the topic context directly, so its field expectations are a contract.

`prds/fixture-topic-context.json` is the agreed shape. These tests seed the golden
three-delta corpus, which ends in a contradiction, so the dispute path is exercised
rather than skipped as an empty list.
"""

import json
import uuid
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

CHARACTER_ENTITY_TYPES = {
    "person",
    "organization",
    "government_body",
    "government_agency",
    "political_party",
    "community_group",
    "media_outlet",
}


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def context() -> dict:
    topic = deepcopy(load_fixture("topic.json"))
    topic["topic_key"] = f"{topic['topic_key']}-{uuid.uuid4().hex}"
    deltas = [
        load_fixture("delta-01-initial.json"),
        load_fixture("delta-02-update.json"),
        load_fixture("delta-03-conflict.json"),
    ]
    for delta in deltas:
        delta["topic_key"] = topic["topic_key"]
        delta["package_id"] = str(uuid.uuid4())

    with TestClient(app) as client:
        topic_response = client.post("/topics", json=topic)
        assert topic_response.status_code == 201
        topic_id = topic_response.json()["topic_id"]
        for delta in deltas:
            assert client.post("/ingestions", json=delta).status_code == 201
        response = client.get(f"/topics/{topic_id}/context")

    assert response.status_code == 200
    return response.json()


def test_collections_layer3_requires_are_lists_of_objects(context: dict) -> None:
    for field in ("entities", "events", "claims", "disputes", "timeline"):
        assert isinstance(context[field], list), f"{field} must be a list"
        assert all(isinstance(item, dict) for item in context[field]), (
            f"Layer 3 rejects the whole response unless every {field} item is an object"
        )


def test_disputes_carry_their_narrative_payload(context: dict) -> None:
    assert context["disputes"], "the golden corpus ends in a contradiction"
    entity_ids = {entity["entity_id"] for entity in context["entities"]}
    claim_ids = {claim["claim_id"] for claim in context["claims"]}
    for dispute in context["disputes"]:
        assert {"dispute_id", "description", "related_entity_ids", "related_claim_ids"}.issubset(dispute)
        assert dispute["description"], "the blueprint uses this as the central conflict"
        assert set(dispute["related_entity_ids"]).issubset(entity_ids)
        assert set(dispute["related_claim_ids"]).issubset(claim_ids)


def test_dispute_descriptions_quote_the_conflicting_claims(context: dict) -> None:
    """The blueprint uses this verbatim as the central conflict, so it must read as prose.

    Internal resolution rationales such as "Same structured subject, predicate, and
    temporal scope with incompatible values." are accurate but unusable in a story.
    """
    claim_texts = {claim["claim_id"]: claim["text"] for claim in context["claims"]}
    for dispute in context["disputes"]:
        related = [
            claim_texts[claim_id].strip().rstrip(".")
            for claim_id in dispute["related_claim_ids"]
        ]
        assert related, "a dispute with no claims cannot be described"
        assert any(text in dispute["description"] for text in related), (
            f"description does not mention what is disputed: {dispute['description']!r}"
        )


def test_claims_name_their_subject(context: dict) -> None:
    entity_ids = {entity["entity_id"] for entity in context["entities"]}
    for claim in context["claims"]:
        assert "subject_ref" in claim, "the world builder ranks protagonists by claim volume"
        if claim["subject_ref"] is not None:
            assert claim["subject_ref"] in entity_ids


def test_events_name_their_participants(context: dict) -> None:
    entity_ids = {entity["entity_id"] for entity in context["entities"]}
    for event in context["events"]:
        assert "participant_entity_ids" in event, "the blueprint maps these onto characters"
        assert set(event["participant_entity_ids"]).issubset(entity_ids)


def test_timeline_entries_are_explicitly_ordered(context: dict) -> None:
    orders = [item["order"] for item in context["timeline"]]
    assert all(isinstance(order, int) for order in orders)
    assert orders == sorted(orders), "the blueprint sorts on order and expects chronology"
    assert len(set(orders)) == len(orders), "duplicate orders make the sort non-deterministic"
    event_ids = {event["event_id"] for event in context["events"]}
    assert all(item["event_id"] in event_ids for item in context["timeline"])


def test_summary_text_is_usable_as_a_conflict_fallback(context: dict) -> None:
    assert isinstance(context["summary"]["text"], str), (
        "a null here becomes the literal string 'None' in the blueprint"
    )
    assert context["summary"]["text"]


def test_interpretations_are_shaped_for_blueprint_themes(context: dict) -> None:
    assert isinstance(context["interpretations"], list)
    for interpretation in context["interpretations"]:
        assert isinstance(interpretation.get("text"), str)
        assert interpretation["text"]


def test_entity_types_are_resolvable_to_characters(context: dict) -> None:
    for entity in context["entities"]:
        assert entity["entity_id"] and entity["label"]
        assert entity["type"]
    assert any(entity["type"] in CHARACTER_ENTITY_TYPES for entity in context["entities"]), (
        "no castable entities means the world builder produces an empty cast"
    )
