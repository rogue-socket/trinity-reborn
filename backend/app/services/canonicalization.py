from copy import deepcopy
from typing import Any, cast

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.policy import (
    CANDIDATE_LIMIT,
    RECONCILIATION_POLICY_VERSION,
    THRESHOLDS,
    canonical_entity_type,
    relationship_type_for_label,
)
from app.models import (
    ArticleVersion,
    CanonicalEntity,
    CanonicalEvent,
    ConfidenceAssessment,
    Claim,
    ClaimAssertion,
    ClaimStatusHistory,
    ClaimMention,
    EntityMention,
    EventMention,
    EventResolutionContext,
    EvidenceMention,
    GraphRelationship,
    IngestionRun,
    LocalIdMapping,
    MappingRevision,
    ProvenanceLink,
    RawPackage,
    RelationshipAssertion,
    RelationshipMention,
    RelationshipStatusHistory,
    ResolutionDecision,
    SourceMention,
)
from app.services.normalization import claim_values_conflict, normalize_claim_value, normalize_text

def _normalized(value: str) -> str:
    return normalize_text(value)


def materialize_new_canonical_objects(
    session: Session,
    raw_package: RawPackage,
    ingestion: IngestionRun,
    topic_id: object,
    report: dict[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(report)
    accepted = {
        (result["local_type"], result["local_id"]): result
        for result in updated["object_results"]
        if result["status"] in {"accepted", "accepted_with_warnings"}
    }
    events_by_local_id: dict[str, CanonicalEvent] = {}

    entities_by_local_id: dict[str, CanonicalEntity] = {}
    canonical: Any
    candidate: Any
    decision: Any
    relationship_type: Any

    for local_type, canonical_type, model in (
        ("source", "source", SourceMention),
        ("article", "article", ArticleVersion),
        ("evidence", "evidence", EvidenceMention),
    ):
        stored_model = cast(Any, model)
        for stored_item in session.scalars(
            select(stored_model).where(stored_model.raw_package_id == raw_package.id)
        ):
            stored_mention = cast(Any, stored_item)
            result = accepted.get((local_type, stored_mention.local_id))
            if result is None:
                continue
            _map_object(
                session,
                raw_package,
                ingestion,
                local_type,
                stored_mention.local_id,
                canonical_type,
                stored_mention.id,
                "CREATE_NEW",
                "stored",
                f"Immutable accepted {local_type} input stored with a Layer 2 ID.",
                result,
            )

    evidence = {
        mention.local_id: mention
        for mention in session.scalars(
            select(EvidenceMention).where(EvidenceMention.raw_package_id == raw_package.id)
        )
    }

    for mention in session.scalars(
        select(EntityMention).where(EntityMention.raw_package_id == raw_package.id)
    ):
        result = accepted.get(("entity", mention.local_id))
        if result is None:
            continue
        canonical = _matching_entity(session, topic_id, mention)
        candidates: list[tuple[object, float]] = []
        if canonical is None:
            canonical = CanonicalEntity(
                canonical_label=mention.label,
                entity_type=canonical_entity_type(mention.source_type),
            )
            session.add(canonical)
            session.flush()
            candidate, score = _possible_entity_match(session, topic_id, mention)
            if candidate is None:
                outcome, classification, rationale = "CREATE_NEW", "new", "No deterministic entity candidate matched."
            else:
                candidates = [(candidate.id, score)]
                _record_possible_match(
                    session, ingestion, topic_id, "entity", canonical.id, candidate.id, "entity_resolution", score,
                    "Normalized label token overlap within the topic.",
                )
                outcome, classification, rationale = (
                    "CREATE_POSSIBLE_MATCH",
                    "possible_match",
                    "Plausible entity candidate retained as a separate canonical object.",
                )
        else:
            candidates = [(canonical.id, 1.0)]
            outcome, classification, rationale = (
                "RESOLVE_TO_EXISTING",
                "matched",
                "Normalized label and entity type matched within the topic.",
            )
        entities_by_local_id[mention.local_id] = canonical
        _map_object(
            session, raw_package, ingestion, "entity", mention.local_id, "entity", canonical.id,
            outcome, classification, rationale, result, candidates=candidates,
        )
        _link_evidence_provenance(
            session, raw_package, "entity", canonical.id, mention.payload, evidence
        )

    for mention in session.scalars(
        select(EventMention).where(EventMention.raw_package_id == raw_package.id)
    ):
        result = accepted.get(("event", mention.local_id))
        if result is None:
            continue
        participant_ids = [
            str(entities_by_local_id[local_id].id)
            for local_id in mention.payload.get("participant_entity_ids", [])
            if local_id in entities_by_local_id
        ]
        location_ids = [
            str(entities_by_local_id[local_id].id)
            for local_id in mention.payload.get("location_entity_ids", [])
            if local_id in entities_by_local_id
        ]
        canonical = _matching_event(session, topic_id, mention, participant_ids, location_ids)
        candidates = []
        if canonical is None:
            canonical = CanonicalEvent(
                topic_id=topic_id,
                display_title=mention.original_title,
                event_type=mention.payload["type"],
            )
            session.add(canonical)
            session.flush()
            session.add(
                EventResolutionContext(
                    event_id=canonical.id,
                    temporal_json=mention.payload.get("temporal", {}),
                    participant_ids=participant_ids,
                    location_ids=location_ids,
                )
            )
            candidate = _possible_event_match(session, topic_id, mention, canonical.id)
            if candidate is None:
                outcome, classification, rationale = "CREATE_NEW", "new", "No deterministic event candidate matched."
            else:
                candidates = [(candidate.id, 0.75)]
                _record_possible_match(
                    session, ingestion, topic_id, "event", canonical.id, candidate.id, "event_resolution", 0.75,
                    "Normalized event title and type match, but time or participants were insufficient for a merge.",
                )
                outcome, classification, rationale = (
                    "CREATE_POSSIBLE_MATCH",
                    "possible_match",
                    "Plausible event candidate retained as a separate canonical object.",
                )
        else:
            candidates = [(canonical.id, 1.0)]
            outcome, classification, rationale = (
                "RESOLVE_TO_EXISTING",
                "matched",
                "Normalized title, type, topic, and exact reported start time matched.",
            )
        events_by_local_id[mention.local_id] = canonical
        _map_object(
            session, raw_package, ingestion, "event", mention.local_id, "event", canonical.id,
            outcome, classification, rationale, result, candidates=candidates,
        )
        _link_evidence_provenance(
            session, raw_package, "event", canonical.id, mention.payload, evidence
        )

    for mention in session.scalars(
        select(ClaimMention).where(ClaimMention.raw_package_id == raw_package.id)
    ):
        result = accepted.get(("claim", mention.local_id))
        if result is None:
            continue
        claim_assertion = None
        derived_assertions: list[RelationshipAssertion] = []
        canonical = _matching_claim(session, topic_id, mention)
        candidates = []
        if canonical is None:
            canonical = Claim(
                topic_id=topic_id,
                original_text=mention.original_text,
                epistemic_status=mention.payload.get("epistemic_status", "unknown"),
                status=(
                    mention.payload["epistemic_status"]
                    if mention.payload.get("epistemic_status") in {"retracted", "superseded"}
                    else "active"
                ),
                canonical_event_id=(
                    events_by_local_id[mention.payload["event_id"]].id
                    if mention.payload.get("event_id") in events_by_local_id
                    else None
                ),
            )
            session.add(canonical)
            session.flush()
            session.add(
                ClaimStatusHistory(
                    claim_id=canonical.id,
                    ingestion_id=ingestion.id,
                    status=canonical.status,
                )
            )
            structured = _structured_claim(session, raw_package, mention)
            has_explicit_update = "corrects_claim_ref" in mention.payload or "retracts_claim_ref" in mention.payload
            contradiction = None if has_explicit_update else _contradicted_claim(session, topic_id, structured)
            progression = None if has_explicit_update else _progressed_claim(session, topic_id, structured)
            if structured is not None:
                claim_assertion = ClaimAssertion(
                    claim_id=canonical.id,
                    derivation_method="normalized_layer1_candidate",
                    input_ids=[
                        str(mention.id),
                        *[
                            str(evidence[evidence_id].id)
                            for evidence_id in mention.payload.get("evidence_ids", [])
                        ],
                    ],
                    confidence=mention.payload.get("confidence", 0.8),
                    processing_version=ingestion.pipeline_version,
                    **structured,
                )
                session.add(claim_assertion)
            if contradiction is None:
                if progression is None:
                    outcome, classification, rationale = "CREATE_NEW", "new", "No deterministic claim candidate matched."
                else:
                    relationship = GraphRelationship(
                        topic_id=topic_id,
                        subject_type="claim",
                        subject_id=canonical.id,
                        object_type="claim",
                        object_id=progression.claim_id,
                        relationship_type="FOLLOWS",
                    )
                    session.add(relationship)
                    session.flush()
                    _record_relationship_status(
                        session,
                        relationship,
                        ingestion,
                        "Derived progression relationship created.",
                    )
                    assertion = RelationshipAssertion(
                        relationship_id=relationship.id,
                        assertion_kind="derived",
                        rationale="Later temporal scope for the same structured subject and predicate.",
                        derivation_method="temporal_progression_rule",
                        input_ids=[str(mention.id), str(progression.claim_id)],
                        confidence=0.9,
                        processing_version=ingestion.pipeline_version,
                    )
                    session.add(assertion)
                    derived_assertions.append(assertion)
                    outcome, classification, rationale = (
                        "CREATE_PROGRESSION",
                        "progression",
                        "Structured claim describes a later state, not a contradiction.",
                    )
            else:
                candidates = [(contradiction.claim_id, 1.0)]
                relationship = GraphRelationship(
                    topic_id=topic_id,
                    subject_type="claim",
                    subject_id=canonical.id,
                    object_type="claim",
                    object_id=contradiction.claim_id,
                    relationship_type="CONTRADICTS",
                    status="possible_contradiction",
                )
                session.add(relationship)
                session.flush()
                possible_assertion = RelationshipAssertion(
                    relationship_id=relationship.id,
                    assertion_kind="derived",
                    status="possible_contradiction",
                    rationale="Same structured subject, predicate, and temporal scope with incompatible values.",
                    derivation_method="structured_contradiction_rule",
                    input_ids=[str(mention.id), str(contradiction.claim_id)],
                    confidence=0.8,
                    processing_version=ingestion.pipeline_version,
                )
                session.add(possible_assertion)
                derived_assertions.append(possible_assertion)
                relationship.status = "confirmed_contradiction"
                _record_relationship_status(
                    session,
                    relationship,
                    ingestion,
                    "Deterministic contradiction checks confirmed the relationship.",
                )
                confirmed_assertion = RelationshipAssertion(
                    relationship_id=relationship.id,
                    assertion_kind="derived",
                    status="confirmed_contradiction",
                    rationale="Structured subject, predicate, temporal scope, and incompatible values all match.",
                    derivation_method="structured_contradiction_rule",
                    input_ids=[str(mention.id), str(contradiction.claim_id)],
                    confidence=1.0,
                    processing_version=ingestion.pipeline_version,
                )
                session.add(confirmed_assertion)
                derived_assertions.append(confirmed_assertion)
                outcome, classification, rationale = (
                    "CREATE_CONFIRMED_CONTRADICTION",
                    "confirmed_contradiction",
                    "Structured claim conflicts with an earlier claim in the same scope and is confirmed by deterministic fields.",
                )
        else:
            candidates = [(canonical.id, 1.0)]
            outcome, classification, rationale = (
                "CREATE_DUPLICATE_LINK",
                "matched",
                "Normalized claim wording matched within the topic.",
            )
        decision = _map_object(
            session, raw_package, ingestion, "claim", mention.local_id, "claim", canonical.id,
            outcome, classification, rationale, result, candidates=candidates,
        )
        if claim_assertion is not None:
            claim_assertion.resolution_decision_id = decision.id
        for assertion in derived_assertions:
            assertion.resolution_decision_id = decision.id
        _link_evidence_provenance(
            session,
            raw_package,
            "claim",
            canonical.id,
            mention.payload,
            evidence,
            claim_id=canonical.id,
        )

    mappings = {
        mapping.local_id: mapping
        for mapping in session.scalars(
            select(LocalIdMapping).where(
                LocalIdMapping.raw_package_id == raw_package.id,
                LocalIdMapping.local_type.in_(("entity", "event", "claim")),
            )
        )
    }
    for mention in session.scalars(
        select(ClaimMention).where(ClaimMention.raw_package_id == raw_package.id)
    ):
        result = accepted.get(("claim", mention.local_id))
        update_field = next(
            (field for field in ("corrects_claim_ref", "retracts_claim_ref") if field in mention.payload),
            None,
        )
        if result is None or update_field is None:
            continue
        incoming = mappings[mention.local_id]
        target = mappings[mention.payload[update_field]]
        target_claim = session.get(Claim, target.canonical_id)
        if target_claim is None:
            raise ValueError("explicit claim update target has no canonical claim")
        relationship_type = "CORRECTS" if update_field == "corrects_claim_ref" else "RETRACTS"
        target_claim.status = "superseded" if relationship_type == "CORRECTS" else "retracted"
        session.add(
            ClaimStatusHistory(
                claim_id=target_claim.id,
                ingestion_id=ingestion.id,
                status=target_claim.status,
            )
        )
        relationship = GraphRelationship(
            topic_id=topic_id,
            subject_type="claim",
            subject_id=incoming.canonical_id,
            object_type="claim",
            object_id=target.canonical_id,
            relationship_type=relationship_type,
        )
        session.add(relationship)
        session.flush()
        _record_relationship_status(
            session,
            relationship,
            ingestion,
            f"Explicit {update_field} relationship created.",
        )
        session.add(
            RelationshipAssertion(
                relationship_id=relationship.id,
                assertion_kind="source_derived",
                rationale=f"Explicit {update_field} in the self-contained package.",
                derivation_method="explicit_layer1_update_reference",
                input_ids=[str(mention.id), str(target.canonical_id)],
                confidence=1.0,
                processing_version=ingestion.pipeline_version,
                resolution_decision_id=incoming.decision_id,
            )
        )
        decision = session.get(ResolutionDecision, incoming.decision_id)
        if decision is None:
            raise ValueError("explicit claim update has no resolution decision")
        outcome = "CREATE_CORRECTION" if relationship_type == "CORRECTS" else "CREATE_RETRACTION"
        decision.outcome = outcome
        decision.rationale = f"Explicit target reference: {update_field}."
        result["classification"] = "correction" if relationship_type == "CORRECTS" else "retraction"
    for mention in session.scalars(
        select(RelationshipMention).where(RelationshipMention.raw_package_id == raw_package.id)
    ):
        result = accepted.get(("relationship", mention.local_id))
        if result is None:
            continue
        relationship_type = _relationship_type(mention.payload["source_relation_label"])
        if relationship_type is None:
            _map_object(
                session,
                raw_package,
                ingestion,
                "relationship",
                mention.local_id,
                "relationship_candidate",
                mention.id,
                "CREATE_NEW",
                "retained_candidate",
                "Unrecognized relationship label retained outside the canonical ontology.",
                result,
            )
            continue
        subject = mappings[mention.payload["subject_ref"]]
        object_ = mappings[mention.payload["object_ref"]]
        temporal_json = mention.payload.get("temporal_scope", {})
        canonical = _matching_relationship(
            session,
            topic_id,
            subject.canonical_type,
            subject.canonical_id,
            object_.canonical_type,
            object_.canonical_id,
            relationship_type,
            temporal_json,
        )
        candidates = []
        if canonical is None:
            canonical = GraphRelationship(
                topic_id=topic_id,
                subject_type=subject.canonical_type,
                subject_id=subject.canonical_id,
                object_type=object_.canonical_type,
                object_id=object_.canonical_id,
                relationship_type=relationship_type,
                temporal_json=temporal_json,
            )
            session.add(canonical)
            session.flush()
            _record_relationship_status(
                session,
                canonical,
                ingestion,
                "Source-derived canonical relationship created.",
            )
            outcome = "CREATE_NEW"
            classification = "new"
            rationale = "No canonical relationship matched the endpoints, type, and temporal scope."
        else:
            candidates = [(canonical.id, 1.0)]
            outcome = "RESOLVE_TO_EXISTING"
            classification = "confirmation"
            rationale = "Independent input supports the existing canonical relationship."
        assertion = RelationshipAssertion(
            relationship_id=canonical.id,
            assertion_kind="source_derived",
            rationale=mention.payload["source_relation_label"],
            derivation_method="normalized_source_relation",
            input_ids=[
                str(mention.id),
                *[
                    str(evidence[evidence_id].id)
                    for evidence_id in mention.payload.get("evidence_ids", [])
                ],
            ],
            confidence=1.0 if candidates else 0.8,
            processing_version=ingestion.pipeline_version,
        )
        session.add(assertion)
        for evidence_id in mention.payload.get("evidence_ids", []):
            session.add(
                ProvenanceLink(
                    graph_object_type="relationship",
                    graph_object_id=canonical.id,
                    evidence_mention_id=evidence[evidence_id].id,
                    raw_package_id=raw_package.id,
                )
            )
        decision = _map_object(
            session, raw_package, ingestion, "relationship", mention.local_id, "relationship", canonical.id,
            outcome, classification, rationale, result, candidates=candidates,
        )
        assertion.resolution_decision_id = decision.id

    updated["summary"]["created"] = sum(
        result.get("classification") == "new" for result in updated["object_results"]
    )
    updated["summary"]["matched"] = sum(
        result.get("classification") in {"matched", "confirmation"}
        for result in updated["object_results"]
    )
    updated["summary"]["contradictions"] = sum(
        result.get("classification") in {"possible_contradiction", "confirmed_contradiction"}
        for result in updated["object_results"]
    )
    return updated


def _matching_entity(session: Session, topic_id: object, mention: EntityMention) -> CanonicalEntity | None:
    entity_type = canonical_entity_type(mention.source_type)
    incoming_names = _entity_mention_names(mention)
    return next(
        (
            candidate
            for candidate, names in _entity_name_index(session, topic_id, entity_type)
            if incoming_names & names
        ),
        None,
    )


def _possible_entity_match(
    session: Session, topic_id: object, mention: EntityMention
) -> tuple[CanonicalEntity | None, float]:
    incoming_names = _entity_mention_names(mention)
    incoming_token_sets = [set(name.split()) for name in incoming_names if name]
    entity_type = canonical_entity_type(mention.source_type)
    if not incoming_token_sets:
        return None, 0.0
    scored = []
    for candidate, names in _entity_name_index(session, topic_id, entity_type):
        candidate_token_sets = [set(name.split()) for name in names if name]
        score = max(
            (
                len(incoming & existing) / len(incoming | existing)
                for incoming in incoming_token_sets
                for existing in candidate_token_sets
                if incoming | existing
            ),
            default=0.0,
        )
        scored.append((candidate, score))
    best_candidate, score = max(
        scored, key=lambda item: item[1], default=(None, 0.0)
    )
    return (
        (best_candidate, score)
        if score >= THRESHOLDS["possible_match"]
        else (None, 0.0)
    )


def _entity_name_index(
    session: Session, topic_id: object, entity_type: str
) -> list[tuple[CanonicalEntity, set[str]]]:
    """Every canonical entity of this type in the topic, with all names it answers to.

    Retrieval is keyed on names rather than an arbitrary window of the topic, so a
    match is never missed just because the counterpart sorts late by canonical id.
    """
    rows = session.execute(
        select(CanonicalEntity, EntityMention)
        .join(LocalIdMapping, CanonicalEntity.id == LocalIdMapping.canonical_id)
        .join(RawPackage, LocalIdMapping.raw_package_id == RawPackage.id)
        .outerjoin(
            EntityMention,
            and_(
                EntityMention.raw_package_id == LocalIdMapping.raw_package_id,
                EntityMention.local_id == LocalIdMapping.local_id,
            ),
        )
        .where(
            RawPackage.topic_id == topic_id,
            CanonicalEntity.entity_type == entity_type,
            LocalIdMapping.local_type == "entity",
        )
        .order_by(CanonicalEntity.id)
    )
    index: dict[Any, tuple[CanonicalEntity, set[str]]] = {}
    for entity, mention in rows:
        _, names = index.setdefault(
            entity.id, (entity, {_normalized(entity.canonical_label)})
        )
        if mention is not None:
            names.update(_entity_mention_names(mention))
    return list(index.values())


def _entity_mention_names(mention: EntityMention) -> set[str]:
    return {
        normalized
        for value in [mention.label, *mention.payload.get("aliases", [])]
        if isinstance(value, str) and (normalized := _normalized(value))
    }


def _matching_event(
    session: Session,
    topic_id: object,
    mention: EventMention,
    participant_ids: list[str],
    location_ids: list[str],
) -> CanonicalEvent | None:
    start = mention.payload.get("temporal", {}).get("start")
    if start is None or not (participant_ids or location_ids):
        return None
    candidates = session.scalars(
        select(CanonicalEvent).where(
            CanonicalEvent.topic_id == topic_id,
            CanonicalEvent.event_type == mention.payload["type"],
            func.lower(CanonicalEvent.display_title) == mention.original_title.casefold(),
        )
        .order_by(CanonicalEvent.id)
        .limit(CANDIDATE_LIMIT)
    )
    for candidate in candidates:
        context = session.get(EventResolutionContext, candidate.id)
        if context is None or context.temporal_json.get("start") != start:
            continue
        if _normalized(candidate.display_title) != _normalized(mention.original_title):
            continue
        shared_participant = set(context.participant_ids) & set(participant_ids)
        shared_location = set(context.location_ids) & set(location_ids)
        if shared_participant or shared_location:
            return candidate
    return None


def _possible_event_match(
    session: Session, topic_id: object, mention: EventMention, incoming_id: object
) -> CanonicalEvent | None:
    candidates = session.scalars(
        select(CanonicalEvent).where(
            CanonicalEvent.topic_id == topic_id,
            CanonicalEvent.event_type == mention.payload["type"],
            CanonicalEvent.id != incoming_id,
            func.lower(CanonicalEvent.display_title) == mention.original_title.casefold(),
        )
        .order_by(CanonicalEvent.id)
        .limit(CANDIDATE_LIMIT)
    )
    return next(
        (
            candidate
            for candidate in candidates
            if _normalized(candidate.display_title) == _normalized(mention.original_title)
        ),
        None,
    )


def _record_possible_match(
    session: Session,
    ingestion: IngestionRun,
    topic_id: object,
    object_type: str,
    incoming_id: object,
    candidate_id: object,
    dimension: str,
    score: float,
    rationale: str,
) -> None:
    relationship = GraphRelationship(
        topic_id=topic_id,
        subject_type=object_type,
        subject_id=incoming_id,
        object_type=object_type,
        object_id=candidate_id,
        relationship_type="POSSIBLY_SAME_AS",
        status="possible_match",
    )
    session.add(relationship)
    session.flush()
    _record_relationship_status(
        session,
        relationship,
        ingestion,
        "Conservative resolver retained a possible match.",
    )
    session.add(
        RelationshipAssertion(
            relationship_id=relationship.id,
            assertion_kind="derived",
            status="possible_match",
            rationale=rationale,
            derivation_method="bounded_candidate_retrieval",
            input_ids=[str(incoming_id), str(candidate_id)],
            confidence=score,
            processing_version=ingestion.pipeline_version,
        )
    )
    session.add(
        ConfidenceAssessment(
            subject_type=object_type,
            subject_id=incoming_id,
            dimension=dimension,
            value=score,
            assessed_by="layer_2_rule",
            method="bounded_candidate_retrieval",
            model_or_rule_version=ingestion.pipeline_version,
            supporting_ids=[str(incoming_id), str(candidate_id)],
            rationale=rationale,
        )
    )


def _matching_claim(session: Session, topic_id: object, mention: ClaimMention) -> Claim | None:
    candidates = session.scalars(
        select(Claim)
        .where(
            Claim.topic_id == topic_id,
            func.lower(Claim.original_text) == mention.original_text.casefold(),
        )
        .order_by(Claim.id)
        .limit(CANDIDATE_LIMIT)
    )
    return next(
        (candidate for candidate in candidates if _normalized(candidate.original_text) == _normalized(mention.original_text)),
        None,
    )


def _structured_claim(
    session: Session, raw_package: RawPackage, mention: ClaimMention
) -> dict[str, Any] | None:
    payload = mention.payload
    subject_ref = payload.get("subject_ref")
    predicate = payload.get("predicate_candidate")
    if subject_ref is None or predicate is None or "object_ref_or_value" not in payload:
        return None
    subject = session.scalar(
        select(LocalIdMapping).where(
            LocalIdMapping.raw_package_id == raw_package.id,
            LocalIdMapping.local_id == subject_ref,
        )
    )
    if subject is None:
        return None
    object_value = payload["object_ref_or_value"]
    object_mapping = (
        session.scalar(
            select(LocalIdMapping).where(
                LocalIdMapping.raw_package_id == raw_package.id,
                LocalIdMapping.local_type.in_(("entity", "event", "claim")),
                LocalIdMapping.local_id == object_value,
            )
        )
        if isinstance(object_value, str)
        else None
    )
    object_json = (
        {"type": object_mapping.canonical_type, "id": str(object_mapping.canonical_id)}
        if object_mapping is not None
        else normalize_claim_value(object_value, payload.get("temporal_scope", {}))
    )
    return {
        "subject_type": subject.canonical_type,
        "subject_id": subject.canonical_id,
        "predicate": _normalized(predicate),
        "object_json": object_json,
        "temporal_json": payload.get("temporal_scope", {}),
    }


def _contradicted_claim(
    session: Session, topic_id: object, structured: dict[str, Any] | None
) -> ClaimAssertion | None:
    if structured is None:
        return None
    candidates = session.scalars(
        select(ClaimAssertion)
        .join(Claim, ClaimAssertion.claim_id == Claim.id)
        .where(
            Claim.topic_id == topic_id,
            ClaimAssertion.subject_type == structured["subject_type"],
            ClaimAssertion.subject_id == structured["subject_id"],
            ClaimAssertion.predicate == structured["predicate"],
        )
        .order_by(ClaimAssertion.id)
        .limit(CANDIDATE_LIMIT)
    )
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.temporal_json == structured["temporal_json"]
            and claim_values_conflict(candidate.object_json, structured["object_json"])
        ),
        None,
    )


def _progressed_claim(
    session: Session, topic_id: object, structured: dict[str, Any] | None
) -> ClaimAssertion | None:
    if structured is None:
        return None
    start = structured["temporal_json"].get("start")
    if start is None:
        return None
    candidates = session.scalars(
        select(ClaimAssertion)
        .join(Claim, ClaimAssertion.claim_id == Claim.id)
        .where(
            Claim.topic_id == topic_id,
            ClaimAssertion.subject_type == structured["subject_type"],
            ClaimAssertion.subject_id == structured["subject_id"],
            ClaimAssertion.predicate == structured["predicate"],
        )
        .order_by(ClaimAssertion.id)
        .limit(CANDIDATE_LIMIT)
    )
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.object_json != structured["object_json"]
            and candidate.temporal_json.get("start") is not None
            and candidate.temporal_json["start"] < start
        ),
        None,
    )


def _relationship_type(source_label: str) -> str | None:
    return relationship_type_for_label(source_label)


def _matching_relationship(
    session: Session,
    topic_id: object,
    subject_type: str,
    subject_id: object,
    object_type: str,
    object_id: object,
    relationship_type: str,
    temporal_json: dict[str, Any],
) -> GraphRelationship | None:
    return session.scalar(
        select(GraphRelationship)
        .where(
            GraphRelationship.topic_id == topic_id,
            GraphRelationship.subject_type == subject_type,
            GraphRelationship.subject_id == subject_id,
            GraphRelationship.object_type == object_type,
            GraphRelationship.object_id == object_id,
            GraphRelationship.relationship_type == relationship_type,
            GraphRelationship.temporal_json == temporal_json,
        )
        .order_by(GraphRelationship.id)
        .limit(CANDIDATE_LIMIT)
    )


def _record_relationship_status(
    session: Session,
    relationship: GraphRelationship,
    ingestion: IngestionRun,
    reason: str,
) -> None:
    session.add(
        RelationshipStatusHistory(
            relationship_id=relationship.id,
            ingestion_id=ingestion.id,
            status=relationship.status,
            reason=reason,
        )
    )


def _link_evidence_provenance(
    session: Session,
    raw_package: RawPackage,
    graph_object_type: str,
    graph_object_id: object,
    payload: dict[str, Any],
    evidence: dict[str, EvidenceMention],
    claim_id: object | None = None,
) -> None:
    for evidence_id in payload.get("evidence_ids", []):
        session.add(
            ProvenanceLink(
                graph_object_type=graph_object_type,
                graph_object_id=graph_object_id,
                evidence_mention_id=evidence[evidence_id].id,
                claim_id=claim_id,
                raw_package_id=raw_package.id,
            )
        )


def _map_object(
    session: Session,
    raw_package: RawPackage,
    ingestion: IngestionRun,
    local_type: str,
    local_id: str,
    canonical_type: str,
    canonical_id: object,
    outcome: str,
    classification: str,
    rationale: str,
    result: dict[str, Any],
    candidates: list[tuple[object, float]] | None = None,
) -> ResolutionDecision:
    confidence, method = _resolution_confidence(classification)
    candidate_items = [
        {"canonical_id": str(candidate_id), "score": score}
        for candidate_id, score in (candidates or [])
    ]
    decision = ResolutionDecision(
        ingestion_id=ingestion.id,
        incoming_type=local_type,
        incoming_id=local_id,
        outcome=outcome,
        rationale=rationale,
        signals_json={
            "input_schema_version": ingestion.input_schema_version,
            "graph_model_version": ingestion.graph_model_version,
            "pipeline_version": ingestion.pipeline_version,
            "ontology_version": ingestion.ontology_version,
            "candidate_policy_version": RECONCILIATION_POLICY_VERSION,
            "candidate_limit": CANDIDATE_LIMIT,
            "selected_canonical_id": str(canonical_id),
            "candidates": candidate_items,
        },
        input_schema_version=ingestion.input_schema_version,
        graph_model_version=ingestion.graph_model_version,
        processing_version=ingestion.pipeline_version,
        ontology_version=ingestion.ontology_version,
    )
    session.add(decision)
    session.flush()
    mapping = LocalIdMapping(
        raw_package_id=raw_package.id,
        local_type=local_type,
        local_id=local_id,
        canonical_type=canonical_type,
        canonical_id=canonical_id,
        decision_id=decision.id,
    )
    session.add(mapping)
    session.flush()
    session.add(
        MappingRevision(
            mapping_id=mapping.id,
            canonical_type=canonical_type,
            canonical_id=canonical_id,
            decision_id=decision.id,
        )
    )
    session.add(
        ProvenanceLink(
            graph_object_type=canonical_type,
            graph_object_id=canonical_id,
            claim_id=canonical_id if canonical_type == "claim" else None,
            raw_package_id=raw_package.id,
        )
    )
    confidence_value = candidates[0][1] if candidates else confidence
    if result["status"] == "accepted_with_warnings":
        confidence_value = min(confidence_value, 0.6)
        method = "evidence_warning_cap"
    session.add(
        ConfidenceAssessment(
            subject_type=canonical_type,
            subject_id=canonical_id,
            dimension={
                "source": "extraction",
                "article": "extraction",
                "evidence": "extraction",
                "entity": "entity_resolution",
                "event": "event_resolution",
                "claim": "claim_support",
                "relationship": "relationship_resolution",
                "relationship_candidate": "relationship_resolution",
            }[canonical_type],
            value=confidence_value,
            assessed_by="layer_2_rule",
            method=(
                "bounded_candidate_retrieval"
                if result["status"] == "accepted" and candidates and candidates[0][1] < 1
                else method
            ),
            model_or_rule_version=ingestion.pipeline_version,
            supporting_ids=[
                str(raw_package.id),
                *(str(candidate_id) for candidate_id, _ in (candidates or [])),
            ],
            rationale=rationale,
        )
    )
    result["canonical_id"] = str(canonical_id)
    result["classification"] = classification
    result["decision_id"] = str(decision.id)
    return decision


def _resolution_confidence(classification: str) -> tuple[float, str]:
    if classification in {"stored", "matched", "confirmation"}:
        return 1.0, "deterministic_exact_match"
    if classification in {"possible_match", "possible_contradiction"}:
        return 0.75, "bounded_candidate_retrieval"
    return 0.8, "no_match_in_bounded_candidates"
