"""Regression coverage for complete deterministic candidate scans."""

import uuid

from sqlalchemy.orm import Session

from backend.shared.db import get_engine
from backend.layer2.models import (
    CanonicalEvent,
    Claim,
    ClaimAssertion,
    EventMention,
    EventResolutionContext,
    Topic,
)
from backend.layer2.services.canonicalization import _contradicted_claim, _matching_event, _progressed_claim


def _topic() -> Topic:
    return Topic(
        topic_key=f"candidate-window-{uuid.uuid4().hex}",
        display_name="Candidate-window regression topic",
        scope_json={},
    )


def _assertion(
    *,
    topic_id: uuid.UUID,
    assertion_id: uuid.UUID,
    subject_id: uuid.UUID,
    object_json: dict[str, str],
    temporal_json: dict[str, str],
) -> ClaimAssertion:
    claim_id = uuid.uuid4()
    claim = Claim(
        id=claim_id,
        topic_id=topic_id,
        original_text=f"Claim {uuid.uuid4().hex}",
        epistemic_status="reported",
    )
    return ClaimAssertion(
        id=assertion_id,
        claim_id=claim_id,
        subject_type="entity",
        subject_id=subject_id,
        predicate="reported",
        object_json=object_json,
        temporal_json=temporal_json,
        derivation_method="test",
        input_ids=[],
        confidence=1.0,
        processing_version="test",
    ), claim


def test_event_and_claim_scans_do_not_stop_at_the_legacy_window() -> None:
    with Session(get_engine()) as session:
        topic = _topic()
        session.add(topic)
        session.flush()

        participant_id = uuid.uuid4()
        event_ids = sorted(uuid.uuid4() for _ in range(12))
        for index, event_id in enumerate(event_ids):
            session.add(
                CanonicalEvent(
                    id=event_id,
                    topic_id=topic.id,
                    display_title="Repeated briefing",
                    event_type="meeting",
                )
            )
            session.add(
                EventResolutionContext(
                    event_id=event_id,
                    temporal_json={"start": "2026-07-01"},
                    participant_ids=[str(participant_id)] if index == len(event_ids) - 1 else [],
                    location_ids=[],
                )
            )

        subject_id = uuid.uuid4()
        same_time = {"start": "2026-07-02"}
        contradiction_ids = sorted(uuid.uuid4() for _ in range(12))
        contradiction_target_id = contradiction_ids[-1]
        for assertion_id in contradiction_ids:
            assertion, claim = _assertion(
                topic_id=topic.id,
                assertion_id=assertion_id,
                subject_id=subject_id,
                object_json={"type": "literal", "value": "different"}
                if assertion_id == contradiction_target_id
                else {"type": "literal", "value": "incoming"},
                temporal_json=same_time,
            )
            session.add_all([claim, assertion])

        progression_ids = sorted(uuid.uuid4() for _ in range(12))
        progression_target_id = progression_ids[-1]
        for assertion_id in progression_ids:
            assertion, claim = _assertion(
                topic_id=topic.id,
                assertion_id=assertion_id,
                subject_id=subject_id,
                object_json={"type": "literal", "value": "previous"},
                temporal_json={"start": "2026-07-01"}
                if assertion_id == progression_target_id
                else {"start": "2026-07-03"},
            )
            session.add_all([claim, assertion])
        session.flush()

        event = _matching_event(
            session,
            topic.id,
            EventMention(
                raw_package_id=uuid.uuid4(),
                local_id="incoming-event",
                original_title="repeated  briefing",
                original_description=None,
                payload={"type": "meeting", "temporal": {"start": "2026-07-01"}},
            ),
            [str(participant_id)],
            [],
        )
        contradiction = _contradicted_claim(
            session,
            topic.id,
            {
                "subject_type": "entity",
                "subject_id": subject_id,
                "predicate": "reported",
                "object_json": {"type": "literal", "value": "incoming"},
                "temporal_json": same_time,
            },
        )
        progression = _progressed_claim(
            session,
            topic.id,
            {
                "subject_type": "entity",
                "subject_id": subject_id,
                "predicate": "reported",
                "object_json": {"type": "literal", "value": "incoming"},
                "temporal_json": {"start": "2026-07-02"},
            },
        )

        assert event is not None and event.id == event_ids[-1]
        assert contradiction is not None and contradiction.id == contradiction_target_id
        assert progression is not None and progression.id == progression_target_id
