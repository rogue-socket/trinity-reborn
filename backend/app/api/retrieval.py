import base64
import binascii
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    CanonicalEntity,
    CanonicalEvent,
    ConfidenceAssessment,
    Claim,
    ClaimAssertion,
    ClaimStatusHistory,
    ClaimMention,
    EvidenceMention,
    EventResolutionContext,
    GraphRelationship,
    IngestionRun,
    LocalIdMapping,
    ProvenanceLink,
    RawPackage,
    ResolutionDecision,
    RelationshipStatusHistory,
    Topic,
    TopicAnnotation,
    TopicLifecycleTransition,
)
from app.services.reconciliation import current_mapping_target

router = APIRouter(tags=["retrieval"])


def _topic_or_404(session: Session, topic_id: uuid.UUID) -> Topic:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="unknown topic_id")
    return topic


def _topic_status(session: Session, topic: Topic, as_of: datetime | None) -> str:
    if as_of is None:
        return topic.status
    transition = session.scalar(
        select(TopicLifecycleTransition)
        .where(
            TopicLifecycleTransition.topic_id == topic.id,
            TopicLifecycleTransition.created_at <= as_of,
        )
        .order_by(
            TopicLifecycleTransition.created_at.desc(),
            TopicLifecycleTransition.id.desc(),
        )
        .limit(1)
    )
    return transition.to_status if transition is not None else "active"


def _topic_entity_ids(
    session: Session, topic_id: uuid.UUID, as_of: datetime | None
) -> set[uuid.UUID]:
    mappings = session.scalars(
        select(LocalIdMapping)
        .join(RawPackage, RawPackage.id == LocalIdMapping.raw_package_id)
        .where(
            RawPackage.topic_id == topic_id,
            LocalIdMapping.local_type == "entity",
        )
    )
    entity_ids: set[uuid.UUID] = set()
    for mapping in mappings:
        try:
            revision = current_mapping_target(session, mapping.id, as_of=as_of)
        except ValueError:
            continue
        if revision.canonical_type == "entity":
            entity_ids.add(revision.canonical_id)
    return entity_ids


def _claim_items(session: Session, topic_id: uuid.UUID, as_of: datetime | None) -> list[dict]:
    claims = list(session.scalars(select(Claim).where(Claim.topic_id == topic_id)))
    statuses = {claim.id: claim.status for claim in claims}
    if as_of is not None and claims:
        histories = session.scalars(
            select(ClaimStatusHistory)
            .where(
                ClaimStatusHistory.claim_id.in_([claim.id for claim in claims]),
                ClaimStatusHistory.effective_at <= as_of,
            )
            .order_by(ClaimStatusHistory.effective_at)
        )
        statuses = {history.claim_id: history.status for history in histories}
        claims = [claim for claim in claims if claim.id in statuses]
    items = []
    for claim in claims:
        assertion = session.scalar(
            select(ClaimAssertion)
            .where(ClaimAssertion.claim_id == claim.id)
            .order_by(ClaimAssertion.id)
            .limit(1)
        )
        mention = session.scalar(
            select(ClaimMention)
            .join(
                LocalIdMapping,
                (LocalIdMapping.raw_package_id == ClaimMention.raw_package_id)
                & (LocalIdMapping.local_type == "claim")
                & (LocalIdMapping.local_id == ClaimMention.local_id),
            )
            .where(LocalIdMapping.canonical_id == claim.id)
            .order_by(ClaimMention.id)
            .limit(1)
        )
        items.append({
            "claim_id": str(claim.id),
            "text": claim.original_text,
            "epistemic_status": claim.epistemic_status,
            "status": statuses[claim.id],
            "event_id": str(claim.canonical_event_id) if claim.canonical_event_id else None,
            "temporal": (
                assertion.temporal_json
                if assertion
                else mention.payload.get("temporal_scope", {})
                if mention
                else {}
            ),
            "confidence": _confidence_items(session, "claim", claim.id, as_of),
            "support": _support_summary(session, "claim", claim.id, as_of),
        })
    return items


def _event_item(session: Session, event: CanonicalEvent, as_of: datetime | None = None) -> dict:
    context = session.get(EventResolutionContext, event.id)
    return {
        "event_id": str(event.id),
        "title": event.display_title,
        "type": event.event_type,
        "status": event.status,
        "temporal": context.temporal_json if context else {},
        "confidence": _confidence_items(session, "event", event.id, as_of),
        "support": _support_summary(session, "event", event.id, as_of),
    }


def _confidence_items(
    session: Session,
    subject_type: str,
    subject_id: uuid.UUID,
    as_of: datetime | None = None,
) -> list[dict]:
    statement = select(ConfidenceAssessment).where(
        ConfidenceAssessment.subject_type == subject_type,
        ConfidenceAssessment.subject_id == subject_id,
    )
    if as_of is not None:
        statement = statement.where(ConfidenceAssessment.created_at <= as_of)
    assessments = session.scalars(
        statement.order_by(ConfidenceAssessment.created_at, ConfidenceAssessment.id)
    )
    latest_by_dimension = {assessment.dimension: assessment for assessment in assessments}
    return [
        {"dimension": assessment.dimension, "value": assessment.value, "method": assessment.method}
        for assessment in latest_by_dimension.values()
    ]


def _meets_minimum_confidence(
    session: Session,
    subject_type: str,
    subject_id: uuid.UUID,
    minimum: float,
    as_of: datetime | None,
) -> bool:
    required_dimension = {
        "entity": "entity_resolution",
        "event": "event_resolution",
        "claim": "claim_support",
        "relationship": "relationship_resolution",
    }[subject_type]
    return any(
        item["dimension"] == required_dimension and item["value"] >= minimum
        for item in _confidence_items(session, subject_type, subject_id, as_of)
    )


def _support_summary(
    session: Session,
    subject_type: str,
    subject_id: uuid.UUID,
    as_of: datetime | None = None,
) -> dict:
    statement = (
        select(ProvenanceLink.raw_package_id)
        .join(RawPackage, RawPackage.id == ProvenanceLink.raw_package_id)
        .where(
            ProvenanceLink.graph_object_type == subject_type,
            ProvenanceLink.graph_object_id == subject_id,
        )
    )
    if as_of is not None:
        statement = statement.where(RawPackage.received_at <= as_of)
    package_ids = set(session.scalars(statement))
    return {
        "package_count": len(package_ids),
        "assessment": "corroborated" if len(package_ids) > 1 else "single_package",
    }


def _relationship_statuses(
    session: Session,
    relationships: list[GraphRelationship],
    as_of: datetime | None,
) -> dict[uuid.UUID, str]:
    if as_of is None:
        return {relationship.id: relationship.status for relationship in relationships}
    if not relationships:
        return {}
    histories = session.scalars(
        select(RelationshipStatusHistory)
        .where(
            RelationshipStatusHistory.relationship_id.in_(
                [relationship.id for relationship in relationships]
            ),
            RelationshipStatusHistory.effective_at <= as_of,
        )
        .order_by(
            RelationshipStatusHistory.effective_at,
            RelationshipStatusHistory.id,
        )
    )
    statuses = {history.relationship_id: history.status for history in histories}
    return {
        relationship.id: statuses.get(relationship.id, relationship.status)
        for relationship in relationships
    }


def _annotations(session: Session, topic_id: uuid.UUID, kind: str, as_of: datetime | None) -> list[dict]:
    statement = select(TopicAnnotation).where(
        TopicAnnotation.topic_id == topic_id,
        TopicAnnotation.kind == kind,
    )
    if as_of is not None:
        statement = statement.where(TopicAnnotation.created_at <= as_of)
    annotations = session.scalars(statement.order_by(TopicAnnotation.created_at, TopicAnnotation.id))
    if kind == "uncertainties":
        return [
            {"text": item.payload.get("text") or item.payload.get("description"), "status": "uncertain"}
            for item in annotations
            if item.payload.get("text") or item.payload.get("description")
        ]
    return [
        {"label": item.payload.get("label") or item.payload.get("text"), "interpretive": True}
        for item in annotations
        if item.payload.get("label") or item.payload.get("text")
    ]


def _topic_events(session: Session, topic_id: uuid.UUID, as_of: datetime | None = None) -> list[dict]:
    statement = select(CanonicalEvent).where(CanonicalEvent.topic_id == topic_id)
    if as_of is not None:
        statement = statement.where(CanonicalEvent.created_at <= as_of)
    events = [_event_item(session, event, as_of) for event in session.scalars(statement)]
    return sorted(events, key=lambda event: (event["temporal"].get("start") is None, event["temporal"].get("start", "")))


def _in_time_range(
    temporal: dict,
    time_start: datetime | None,
    time_end: datetime | None,
) -> bool:
    value = temporal.get("start")
    if value is None:
        return False
    scope_start = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    scope_end = datetime.fromisoformat(
        str(temporal.get("end", value)).replace("Z", "+00:00")
    )
    return (time_start is None or scope_end >= time_start) and (
        time_end is None or scope_start <= time_end
    )


@router.get("/topics/{topic_id}/timeline")
def get_timeline(
    topic_id: uuid.UUID, as_of: datetime | None = None, session: Session = Depends(get_session)
) -> dict:
    _topic_or_404(session, topic_id)
    return {"topic_id": str(topic_id), "timeline": _topic_events(session, topic_id, as_of)}


@router.get("/topics/{topic_id}/context")
def get_topic_context(
    topic_id: uuid.UUID,
    max_nodes: int = Query(default=200, ge=1, le=200),
    max_relationships: int = Query(default=500, ge=1, le=500),
    include_disputed: bool = True,
    include_interpretations: bool = True,
    minimum_confidence: float | None = Query(default=None, ge=0, le=1),
    time_start: datetime | None = None,
    time_end: datetime | None = None,
    cursor: str | None = None,
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict:
    topic = _topic_or_404(session, topic_id)
    entity_ids = _topic_entity_ids(session, topic_id, as_of)
    entity_statement = select(CanonicalEntity).where(CanonicalEntity.id.in_(entity_ids))
    if as_of is not None:
        entity_statement = entity_statement.where(CanonicalEntity.created_at <= as_of)
    entities = {
        entity.id: entity
        for entity in session.scalars(entity_statement)
    }
    events = _topic_events(session, topic_id, as_of)
    if time_start is not None or time_end is not None:
        events = [
            event
            for event in events
            if _in_time_range(event["temporal"], time_start, time_end)
        ]
    claim_items = _claim_items(session, topic_id, as_of)
    if time_start is not None or time_end is not None:
        claim_items = [
            item
            for item in claim_items
            if _in_time_range(item["temporal"], time_start, time_end)
        ]
    if not include_disputed:
        claim_items = [
            item
            for item in claim_items
            if item["status"] not in {"disputed", "possible_contradiction", "confirmed_contradiction"}
            and item["epistemic_status"] != "disputed"
        ]
    if minimum_confidence is not None:
        entities = {
            entity_id: entity
            for entity_id, entity in entities.items()
            if _meets_minimum_confidence(
                session, "entity", entity_id, minimum_confidence, as_of
            )
        }
        events = [
            event
            for event in events
            if _meets_minimum_confidence(
                session,
                "event",
                uuid.UUID(event["event_id"]),
                minimum_confidence,
                as_of,
            )
        ]
        claim_items = [
            item
            for item in claim_items
            if _meets_minimum_confidence(
                session,
                "claim",
                uuid.UUID(item["claim_id"]),
                minimum_confidence,
                as_of,
            )
        ]
    entity_items = [
        {
            "entity_id": str(entity.id),
            "label": entity.canonical_label,
            "type": entity.entity_type,
            "status": entity.status,
            "confidence": _confidence_items(session, "entity", entity.id, as_of),
            "support": _support_summary(session, "entity", entity.id, as_of),
        }
        for entity in entities.values()
    ]
    degree: dict[uuid.UUID, int] = {}
    for relationship in session.scalars(
        select(GraphRelationship).where(GraphRelationship.topic_id == topic_id)
    ):
        degree[relationship.subject_id] = degree.get(relationship.subject_id, 0) + 1
        degree[relationship.object_id] = degree.get(relationship.object_id, 0) + 1
    nodes = [
        ("event", event)
        for event in sorted(
            events,
            key=lambda item: item["temporal"].get("start", ""),
            reverse=True,
        )
    ]
    nodes.extend(
        ("entity", entity)
        for entity in sorted(
            entity_items,
            key=lambda item: (
                -degree.get(uuid.UUID(str(item["entity_id"])), 0),
                item["entity_id"],
            ),
        )
    )
    nodes.extend(
        ("claim", claim)
        for claim in sorted(
            claim_items,
            key=lambda item: (
                item["status"] not in {"disputed", "possible_contradiction", "confirmed_contradiction"},
                item["claim_id"],
            ),
        )
    )
    node_count = len(nodes)
    offset = _decode_cursor(cursor)
    page = nodes[offset : offset + max_nodes]
    returned_events = sorted(
        [item for kind, item in page if kind == "event"],
        key=lambda item: (
            item["temporal"].get("start") is None,
            item["temporal"].get("start", ""),
        ),
    )
    returned_entities = [item for kind, item in page if kind == "entity"]
    returned_claims = [item for kind, item in page if kind == "claim"]
    returned_ids = {
        uuid.UUID(item["event_id"]) for item in returned_events
    } | {uuid.UUID(item["entity_id"]) for item in returned_entities} | {
        uuid.UUID(item["claim_id"]) for item in returned_claims
    }
    relationship_statement = select(GraphRelationship).where(GraphRelationship.topic_id == topic_id)
    if as_of is not None:
        relationship_statement = relationship_statement.where(GraphRelationship.created_at <= as_of)
    candidate_relationships = list(session.scalars(relationship_statement))
    if time_start is not None or time_end is not None:
        candidate_relationships = [
            relationship
            for relationship in candidate_relationships
            if _in_time_range(relationship.temporal_json, time_start, time_end)
        ]
    if minimum_confidence is not None:
        candidate_relationships = [
            relationship
            for relationship in candidate_relationships
            if _meets_minimum_confidence(
                session,
                "relationship",
                relationship.id,
                minimum_confidence,
                as_of,
            )
        ]
    relationship_statuses = _relationship_statuses(
        session, candidate_relationships, as_of
    )
    relationships = [
        relationship
        for relationship in candidate_relationships
        if relationship.subject_id in returned_ids and relationship.object_id in returned_ids
        and (
            include_disputed
            or (
                relationship_statuses[relationship.id] != "possible_contradiction"
                and relationship.relationship_type != "CONTRADICTS"
            )
        )
    ]
    relationship_count = len(relationships)
    relationships = relationships[:max_relationships]
    actor_roles: dict[uuid.UUID, set[str]] = {
        uuid.UUID(item["entity_id"]): set() for item in returned_entities
    }
    for relationship in relationships:
        if relationship.subject_type == "entity" and relationship.subject_id in actor_roles:
            actor_roles[relationship.subject_id].add(relationship.relationship_type)
    actors = [
        {
            "entity_id": item["entity_id"],
            "label": item["label"],
            "roles": sorted(actor_roles[uuid.UUID(item["entity_id"])]),
        }
        for item in returned_entities
        if actor_roles[uuid.UUID(item["entity_id"])]
    ]
    summary_claims = [
        {"claim_id": item["claim_id"], "text": item["text"], "status": item["status"]}
        for item in claim_items
        if item["status"] == "active"
    ]
    next_cursor = _encode_cursor(offset + max_nodes) if offset + max_nodes < node_count else None
    truncated = next_cursor is not None or relationship_count > max_relationships
    return {
        "topic": {
            "topic_id": str(topic.id),
            "topic_key": topic.topic_key,
            "display_name": topic.display_name,
            "status": _topic_status(session, topic, as_of),
        },
        "summary": {
            "text": None,
            "claim_ids": [item["claim_id"] for item in summary_claims],
            "claims": summary_claims,
        },
        "timeline": returned_events,
        "entities": returned_entities,
        "events": returned_events,
        "claims": returned_claims,
        "relationships": [
            {
                "relationship_id": str(relationship.id),
                "subject": {"type": relationship.subject_type, "id": str(relationship.subject_id)},
                "object": {"type": relationship.object_type, "id": str(relationship.object_id)},
                "type": relationship.relationship_type,
                "status": relationship_statuses[relationship.id],
                "temporal": relationship.temporal_json,
                "confidence": _confidence_items(
                    session, "relationship", relationship.id, as_of
                ),
                "support": _support_summary(
                    session, "relationship", relationship.id, as_of
                ),
            }
            for relationship in relationships
        ],
        "disputes": [
            str(relationship.id)
            for relationship in relationships
            if relationship.relationship_type == "CONTRADICTS"
        ],
        "actors": actors,
        "uncertainties": _annotations(session, topic_id, "uncertainties", as_of),
        "themes": _annotations(session, topic_id, "themes", as_of) if include_interpretations else [],
        "sentiment": _annotations(session, topic_id, "sentiment", as_of) if include_interpretations else [],
        "interpretations": [] if include_interpretations else [],
        "coverage": {
            "returned_nodes": len(returned_ids),
            "returned_relationships": len(relationships),
            "omitted_nodes": max(node_count - (offset + len(page)), 0),
            "truncated": truncated,
            "next_cursor": next_cursor,
        },
        "query_hints": {
            "available_expansions": [
                {
                    "seed_id": str(node_id),
                    "relationship_types": sorted(
                        {
                            relationship.relationship_type
                            for relationship in candidate_relationships
                            if node_id
                            in {relationship.subject_id, relationship.object_id}
                        }
                    ),
                }
                for node_id in sorted(returned_ids, key=str)
                if any(
                    node_id in {relationship.subject_id, relationship.object_id}
                    for relationship in candidate_relationships
                )
            ][:10],
            "raw_export_available": True,
        },
    }


class GraphExpansionRequest(BaseModel):
    topic_id: uuid.UUID
    seed_ids: list[uuid.UUID] = Field(min_length=1)
    relationship_types: list[str] | None = None
    max_depth: int = Field(default=1, ge=1, le=2)
    max_nodes: int = Field(default=100, ge=1, le=100)
    max_relationships: int = Field(default=250, ge=1, le=500)
    include_disputed: bool = True
    statuses: list[str] | None = None
    minimum_confidence: float | None = Field(default=None, ge=0, le=1)
    time_start: datetime | None = None
    time_end: datetime | None = None
    as_of: datetime | None = None


def _topic_node_ids(session: Session, topic_id: uuid.UUID, as_of: datetime | None = None) -> set[uuid.UUID]:
    entity_statement = select(CanonicalEntity.id).where(
        CanonicalEntity.id.in_(_topic_entity_ids(session, topic_id, as_of))
    )
    if as_of is not None:
        entity_statement = entity_statement.where(CanonicalEntity.created_at <= as_of)
    entity_ids = set(
        session.scalars(entity_statement)
    )
    event_statement = select(CanonicalEvent.id).where(CanonicalEvent.topic_id == topic_id)
    if as_of is not None:
        event_statement = event_statement.where(CanonicalEvent.created_at <= as_of)
    event_ids = set(session.scalars(event_statement))
    claim_ids = {uuid.UUID(item["claim_id"]) for item in _claim_items(session, topic_id, as_of)}
    return entity_ids | event_ids | claim_ids


@router.post("/graph/expand")
def expand_graph(payload: GraphExpansionRequest, session: Session = Depends(get_session)) -> dict:
    _topic_or_404(session, payload.topic_id)
    topic_nodes = _topic_node_ids(session, payload.topic_id, payload.as_of)
    if not set(payload.seed_ids).issubset(topic_nodes):
        raise HTTPException(status_code=400, detail="seed IDs must belong to the supplied topic")

    relationship_statement = select(GraphRelationship).where(GraphRelationship.topic_id == payload.topic_id)
    if payload.as_of is not None:
        relationship_statement = relationship_statement.where(GraphRelationship.created_at <= payload.as_of)
    relationships = list(session.scalars(relationship_statement))
    relationship_statuses = _relationship_statuses(
        session, relationships, payload.as_of
    )
    if payload.relationship_types is not None:
        relationships = [
            relationship for relationship in relationships if relationship.relationship_type in payload.relationship_types
        ]
    if payload.statuses is not None:
        relationships = [
            relationship
            for relationship in relationships
            if relationship_statuses[relationship.id] in payload.statuses
        ]
    if payload.time_start is not None or payload.time_end is not None:
        relationships = [
            relationship
            for relationship in relationships
            if _in_time_range(
                relationship.temporal_json, payload.time_start, payload.time_end
            )
        ]
    if payload.minimum_confidence is not None:
        relationships = [
            relationship
            for relationship in relationships
            if _meets_minimum_confidence(
                session,
                "relationship",
                relationship.id,
                payload.minimum_confidence,
                payload.as_of,
            )
        ]
    if not payload.include_disputed:
        relationships = [
            relationship
            for relationship in relationships
            if relationship_statuses[relationship.id]
            not in {"possible_contradiction", "confirmed_contradiction", "disputed"}
            and relationship.relationship_type != "CONTRADICTS"
        ]
    relationships.sort(key=lambda item: (item.relationship_type, str(item.id)))

    visited = set(payload.seed_ids)
    frontier = set(payload.seed_ids)
    included: list[GraphRelationship] = []
    included_ids: set[uuid.UUID] = set()
    for _ in range(payload.max_depth):
        next_frontier: set[uuid.UUID] = set()
        for relationship in relationships:
            endpoints = {relationship.subject_id, relationship.object_id}
            if not endpoints & frontier:
                continue
            if relationship.id in included_ids:
                continue
            if len(included) >= payload.max_relationships:
                continue
            if len(visited | endpoints) > payload.max_nodes:
                continue
            included.append(relationship)
            included_ids.add(relationship.id)
            next_frontier |= endpoints - visited
            visited |= endpoints
        frontier = next_frontier
        if not frontier:
            break

    return {
        "topic_id": str(payload.topic_id),
        "nodes": [
            _node_detail(session, payload.topic_id, node_id, payload.as_of)
            for node_id in sorted(visited, key=str)
        ],
        "relationships": [
            {
                "relationship_id": str(relationship.id),
                "subject_id": str(relationship.subject_id),
                "object_id": str(relationship.object_id),
                "type": relationship.relationship_type,
                "status": relationship_statuses[relationship.id],
                "temporal": relationship.temporal_json,
                "confidence": _confidence_items(
                    session, "relationship", relationship.id, payload.as_of
                ),
                "support": _support_summary(
                    session, "relationship", relationship.id, payload.as_of
                ),
            }
            for relationship in included
        ],
        "coverage": {
            "truncated": len(visited) >= payload.max_nodes
            or len(included) < len(relationships),
            "returned_nodes": len(visited),
            "returned_relationships": len(included),
            "max_depth": payload.max_depth,
        },
    }


def _node_detail(
    session: Session,
    topic_id: uuid.UUID,
    node_id: uuid.UUID,
    as_of: datetime | None,
) -> dict:
    entity = session.get(CanonicalEntity, node_id)
    if entity is not None and node_id in _topic_entity_ids(session, topic_id, as_of):
        return {
            "id": str(entity.id),
            "node_type": "entity",
            "label": entity.canonical_label,
            "entity_type": entity.entity_type,
            "status": entity.status,
            "temporal": {},
            "confidence": _confidence_items(session, "entity", entity.id, as_of),
            "support": _support_summary(session, "entity", entity.id, as_of),
        }
    event = session.get(CanonicalEvent, node_id)
    if event is not None and event.topic_id == topic_id:
        item = _event_item(session, event, as_of)
        return {"id": str(event.id), "node_type": "event", **item}
    claim = next(
        (
            item
            for item in _claim_items(session, topic_id, as_of)
            if item["claim_id"] == str(node_id)
        ),
        None,
    )
    if claim is not None:
        return {"id": str(node_id), "node_type": "claim", **claim}
    raise HTTPException(status_code=400, detail="expanded node is outside the topic")


@router.get("/topics/{topic_id}/raw-export")
def raw_export(
    topic_id: uuid.UUID,
    status: str | None = None,
    event_id: uuid.UUID | None = None,
    claim_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=100),
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict:
    _topic_or_404(session, topic_id)
    statuses = status.split(",") if status else None
    statement = (
        select(ClaimMention, LocalIdMapping, Claim)
        .join(
            LocalIdMapping,
            (LocalIdMapping.raw_package_id == ClaimMention.raw_package_id)
            & (LocalIdMapping.local_type == "claim")
            & (LocalIdMapping.local_id == ClaimMention.local_id),
        )
        .join(Claim, Claim.id == LocalIdMapping.canonical_id)
        .join(RawPackage, RawPackage.id == ClaimMention.raw_package_id)
        .where(RawPackage.topic_id == topic_id)
        .order_by(RawPackage.received_at, ClaimMention.local_id)
    )
    if statuses is not None:
        status_conditions: list[Any] = []
        if "active" in statuses:
            status_conditions.append(
                (Claim.status == "active") & (Claim.epistemic_status != "disputed")
            )
        if "disputed" in statuses:
            status_conditions.append(
                (Claim.status == "disputed") | (Claim.epistemic_status == "disputed")
            )
        status_conditions.extend(
            Claim.status == requested
            for requested in statuses
            if requested in {"superseded", "retracted"}
        )
        statement = statement.where(or_(*status_conditions))
    if event_id is not None:
        statement = statement.where(Claim.canonical_event_id == event_id)
    if claim_id is not None:
        statement = statement.where(Claim.id == claim_id)
    rows = list(
        session.execute(
            statement
        )
    )
    offset = _decode_cursor(cursor)
    page = rows[offset : offset + limit]
    items: list[dict[str, Any]] = []
    partitions: dict[str, list[dict[str, Any]]] = {
        "active": [],
        "disputed": [],
        "superseded": [],
        "retracted": [],
    }
    for mention, mapping, claim in page:
        evidence_ids = mention.payload.get("evidence_ids", [])
        evidence = list(
            session.scalars(
                select(EvidenceMention).where(
                    EvidenceMention.raw_package_id == mention.raw_package_id,
                    EvidenceMention.local_id.in_(evidence_ids),
                )
            )
        )
        canonical_event = (
            session.get(CanonicalEvent, claim.canonical_event_id)
            if claim.canonical_event_id
            else None
        )
        item = {
                "claim_id": str(mapping.canonical_id),
                "status": claim.status,
                "event_id": str(claim.canonical_event_id) if claim.canonical_event_id else None,
                "temporal": (
                    _event_item(session, canonical_event)["temporal"]
                    if canonical_event is not None
                    else {}
                ),
                "raw_text": mention.original_text,
                "evidence": [{"excerpt": item.excerpt} for item in evidence],
                "support": _support_summary(session, "claim", claim.id),
            }
        items.append(item)
        partition = (
            "disputed"
            if claim.epistemic_status == "disputed" or claim.status == "disputed"
            else claim.status
            if claim.status in partitions
            else "active"
        )
        partitions[partition].append(item)
    next_cursor = _encode_cursor(offset + limit) if offset + limit < len(rows) else None
    return {
        "items": items,
        **partitions,
        "next_cursor": next_cursor,
        "truncated": next_cursor is not None,
    }


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        value = base64.urlsafe_b64decode(cursor.encode()).decode()
        prefix, offset = value.split(":", maxsplit=1)
        if prefix != "offset" or int(offset) < 0:
            raise ValueError
        return int(offset)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid cursor")


@router.get("/entities/{entity_id}/context")
def entity_context(
    entity_id: uuid.UUID,
    topic_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> dict:
    _topic_or_404(session, topic_id)
    entity = session.get(CanonicalEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="unknown entity_id")
    in_topic = session.scalar(
        select(LocalIdMapping.id)
        .join(RawPackage, LocalIdMapping.raw_package_id == RawPackage.id)
        .where(
            LocalIdMapping.canonical_type == "entity",
            LocalIdMapping.canonical_id == entity_id,
            RawPackage.topic_id == topic_id,
        )
    )
    if in_topic is None:
        raise HTTPException(status_code=404, detail="entity is not present in this topic")
    claims = list(
        session.scalars(
            select(Claim)
            .join(ClaimAssertion, ClaimAssertion.claim_id == Claim.id)
            .where(
                Claim.topic_id == topic_id,
                ClaimAssertion.subject_type == "entity",
                ClaimAssertion.subject_id == entity_id,
            )
        )
    )
    relationships = list(
        session.scalars(
            select(GraphRelationship).where(
                GraphRelationship.topic_id == topic_id,
                (GraphRelationship.subject_id == entity_id) | (GraphRelationship.object_id == entity_id),
            )
        )
    )
    return {
        "entity": {
            "entity_id": str(entity.id),
            "label": entity.canonical_label,
            "type": entity.entity_type,
            "status": entity.status,
        },
        "claims": [
            {"claim_id": str(claim.id), "text": claim.original_text, "status": claim.status}
            for claim in claims
        ],
        "relationships": [
            {
                "relationship_id": str(relationship.id),
                "type": relationship.relationship_type,
                "status": relationship.status,
                "subject_id": str(relationship.subject_id),
                "object_id": str(relationship.object_id),
            }
            for relationship in relationships
        ],
    }


@router.get("/claims/{claim_id}/evidence")
def claim_evidence(claim_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="unknown claim_id")
    rows = list(
        session.execute(
            select(ClaimMention)
            .join(
                LocalIdMapping,
                (LocalIdMapping.raw_package_id == ClaimMention.raw_package_id)
                & (LocalIdMapping.local_type == "claim")
                & (LocalIdMapping.local_id == ClaimMention.local_id),
            )
            .where(LocalIdMapping.canonical_id == claim_id)
        )
    )
    evidence: list[dict[str, str]] = []
    for (mention,) in rows:
        evidence_ids = mention.payload.get("evidence_ids", [])
        evidence.extend(
            {"excerpt": item.excerpt}
            for item in session.scalars(
                select(EvidenceMention).where(
                    EvidenceMention.raw_package_id == mention.raw_package_id,
                    EvidenceMention.local_id.in_(evidence_ids),
                )
            )
        )
    return {
        "claim_id": str(claim.id),
        "text": claim.original_text,
        "status": claim.status,
        "epistemic_status": claim.epistemic_status,
        "evidence": evidence,
    }


@router.get("/ingestions/{ingestion_id}")
def ingestion_report(ingestion_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    run = session.get(IngestionRun, ingestion_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown ingestion_id")
    raw_package = session.get(RawPackage, run.raw_package_id)
    if raw_package is None:
        raise HTTPException(status_code=500, detail="ingestion has no raw package")
    decisions = list(
        session.scalars(
            select(ResolutionDecision)
            .where(ResolutionDecision.ingestion_id == run.id)
            .order_by(ResolutionDecision.created_at, ResolutionDecision.id)
        )
    )
    return {
        "ingestion_id": str(run.id),
        "package_id": str(raw_package.package_id),
        "topic_id": str(raw_package.topic_id),
        "status": run.status,
        "input_schema_version": run.input_schema_version,
        "pipeline_version": run.pipeline_version,
        "graph_model_version": run.graph_model_version,
        "ontology_version": run.ontology_version,
        "received_delta": raw_package.payload,
        "report": run.report_json,
        "resolution_decisions": [
            {
                "decision_id": str(decision.id),
                "incoming_type": decision.incoming_type,
                "incoming_id": decision.incoming_id,
                "outcome": decision.outcome,
                "rationale": decision.rationale,
                "signals": decision.signals_json,
                "input_schema_version": decision.input_schema_version,
                "graph_model_version": decision.graph_model_version,
                "processing_version": decision.processing_version,
                "ontology_version": decision.ontology_version,
                "supersedes_decision_id": (
                    str(decision.supersedes_decision_id)
                    if decision.supersedes_decision_id
                    else None
                ),
            }
            for decision in decisions
        ],
    }
