import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    LocalIdMapping,
    MappingRevision,
    RawPackage,
    ResolutionDecision,
)


def current_mapping_target(
    session: Session,
    mapping_id: uuid.UUID,
    as_of: datetime | None = None,
) -> MappingRevision:
    statement = select(MappingRevision).where(MappingRevision.mapping_id == mapping_id)
    if as_of is not None:
        statement = statement.where(MappingRevision.created_at <= as_of)
    revision = session.scalar(
        statement.order_by(
            MappingRevision.created_at.desc(), MappingRevision.id.desc()
        ).limit(1)
    )
    if revision is None:
        raise ValueError("mapping has no revision at the requested time")
    return revision


def reverse_mapping(
    session: Session,
    *,
    mapping_id: uuid.UUID,
    canonical_type: str,
    canonical_id: uuid.UUID,
    rationale: str,
) -> ResolutionDecision:
    mapping = session.get(LocalIdMapping, mapping_id)
    if mapping is None:
        raise ValueError("unknown mapping_id")
    current = current_mapping_target(session, mapping.id)
    if current.canonical_type == canonical_type and current.canonical_id == canonical_id:
        raise ValueError("replacement target is already current")

    topic_id = session.scalar(
        select(RawPackage.topic_id).where(RawPackage.id == mapping.raw_package_id)
    )
    replacement_exists = session.scalar(
        select(LocalIdMapping.id)
        .join(RawPackage, RawPackage.id == LocalIdMapping.raw_package_id)
        .where(
            RawPackage.topic_id == topic_id,
            LocalIdMapping.canonical_type == canonical_type,
            LocalIdMapping.canonical_id == canonical_id,
        )
        .limit(1)
    )
    if replacement_exists is None:
        raise ValueError("replacement target must already belong to the same topic")

    previous_decision = session.get(ResolutionDecision, current.decision_id)
    if previous_decision is None:
        raise ValueError("current mapping revision has no decision")
    decision = ResolutionDecision(
        ingestion_id=previous_decision.ingestion_id,
        incoming_type=previous_decision.incoming_type,
        incoming_id=previous_decision.incoming_id,
        outcome="RESOLVE_TO_EXISTING",
        rationale=rationale,
        signals_json={
            **previous_decision.signals_json,
            "reversal": True,
            "previous_canonical_id": str(current.canonical_id),
            "selected_canonical_id": str(canonical_id),
        },
        input_schema_version=previous_decision.input_schema_version,
        graph_model_version=previous_decision.graph_model_version,
        processing_version=previous_decision.processing_version,
        ontology_version=previous_decision.ontology_version,
        supersedes_decision_id=previous_decision.id,
    )
    session.add(decision)
    session.flush()
    session.add(
        MappingRevision(
            mapping_id=mapping.id,
            canonical_type=canonical_type,
            canonical_id=canonical_id,
            decision_id=decision.id,
            supersedes_revision_id=current.id,
        )
    )
    session.flush()
    return decision
